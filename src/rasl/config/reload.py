"""Live reload: turn a change to the config files into an update of the running plan.

A ``ConfigSession`` keeps the config as last loaded. ``reload()`` loads the files
again, asks knobly what changed between the two renders, and sorts those changes
by node:

- a node only in the new config is **added**; one only in the old is **removed**;
- a node whose own line changed (its type or positional values), or whose
  settings changed and that cannot take them in place, is **restarted**: the
  running object is stopped and a new one is built and started;
- a node whose settings changed and whose class defines ``update_config`` is
  **updated** in place: it keeps running and is handed its new config;
- a node whose ``connect`` lines alone changed is **rerouted**: it keeps running
  and only the routing around it is rebuilt;
- every other node is untouched and keeps running.

A node is known by its id, so moving its lines around changes nothing, and a
changed ``@set`` variable or included file shows up as changes to the nodes that
read it. A reload that fails for any reason changes nothing: the session keeps
the last good config, and the caller keeps the running plan.

Example:
    >>> session = ConfigSession("config.conf")
    >>> scheduler = UnifiedScheduler(session.plan)
    >>> # ... later, after config.conf was edited:
    >>> update = session.reload()
    >>> if update is not None:
    ...     scheduler.request_update(update)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rasl.config.document import Directive, Rendered, load_document
from rasl.config.loader import _node_spec, build_plan, graph_directive, node_id_of
from rasl.engine.graph import ExecutionPlan
from rasl.engine.registry import get_node_class

_CONNECTION_KEYWORDS = ("connect", "edge")
"""The lines in a node's block that describe routing, not the node's settings."""


@dataclass(frozen=True)
class PlanUpdate:
    """A new plan, and how it differs from the one running.

    Node ids appear in at most one of ``added``, ``removed``, ``restarted``,
    ``updated`` and ``rerouted``.

    Attributes:
        plan: The new plan. Nodes that keep running are the same objects as in
            the old plan.
        added: Nodes to start.
        removed: Nodes to stop.
        restarted: Nodes to stop, whose new objects (in ``plan``) are then started.
        updated: New configs, by node id, for running nodes to take in place
            (``node.update_config(config)``).
        rerouted: Running nodes whose connections alone changed.
        changes: Every change knobly found, for people, such as
            ``changed graph > node "leds" > max_count``.
        ignored: The changes among them that are outside any node and so have no
            effect until a restart (the ``ui`` block, for one).
    """

    plan: ExecutionPlan
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    restarted: tuple[str, ...] = ()
    updated: Mapping[str, Any] = field(default_factory=dict)
    rerouted: tuple[str, ...] = ()
    changes: tuple[str, ...] = ()
    ignored: tuple[str, ...] = ()


def _is_graph_node(directive: Directive) -> bool:
    """True for a ``node`` written directly in a top-level ``graph`` block."""
    parent = directive.parent
    return (
        directive.name == "node"
        and parent is not None
        and parent.name == "graph"
        and parent.parent is None
    )


def _node_key(directive: Directive) -> str | None:
    """knobly's key rule for rasl: a graph's node is known by its id."""
    return node_id_of(directive) if _is_graph_node(directive) else None


class ConfigSession:
    """A config file as last loaded, and the plan built from it.

    Attributes:
        path: The root config file.
        tree: The last good render of it (knobly's rendered tree).
        plan: The plan built from that render.
    """

    def __init__(self, path: str | Path) -> None:
        """Load the config and build its plan.

        Raises:
            ConfigError: If the config is invalid.
            FileNotFoundError: If the file doesn't exist.
        """
        self.path = Path(path)
        self.tree: Rendered = load_document(self.path)
        self.plan: ExecutionPlan = build_plan(self.tree)[0]

    @property
    def documents(self) -> tuple[str, ...]:
        """Every file the last good load read: the root and the files it includes."""
        return tuple(self.tree.graph.documents)

    def reload(self) -> PlanUpdate | None:
        """Load the files again and work out how the plan changes.

        Returns:
            The update to hand to the scheduler, or None when nothing a program
            reads changed (a comment, the layout, a quote style).

        Raises:
            ConfigError: If the config is now invalid.
            Exception: Whatever else building the new plan raises (an unknown
                node in a ``connect``, a duplicate id, ...). In every case the
                session, the plan and the running nodes are left as they were.
        """
        tree = load_document(self.path)
        changes = self.tree.diff(tree, key=_node_key)
        if not changes:
            self.tree = tree  # the same directives, at their new places in the files
            return None

        old_nodes = self.plan.nodes
        added: set[str] = set()
        removed: set[str] = set()
        replaced: set[str] = set()  # the node's own line changed
        settings: set[str] = set()
        connections: set[str] = set()
        ignored: list[str] = []

        for change in changes:
            directive = change.before if change.kind == "removed" or change.kind == "unknown" else change.after
            node = directive.closest(_is_graph_node)
            node_id = node_id_of(node) if node is not None else None
            if node is None or node_id is None:
                ignored.append(f"{change.kind} {change.address}")
            elif directive is node:
                {"added": added, "removed": removed}.get(change.kind, replaced).add(node_id)
            elif directive.closest(
                lambda d: d.name in _CONNECTION_KEYWORDS and d.parent is node
            ):
                connections.add(node_id)
            else:
                settings.add(node_id)

        # An id both removed and added (two nodes swapped ids, say) is a replacement
        replaced |= added & removed
        added -= replaced
        removed -= replaced
        # Only a node now running can be stopped, replaced or kept
        added |= {n for n in replaced | settings | connections if n not in old_nodes}
        removed &= old_nodes.keys()

        new_directives = {
            node_id_of(d): d for d in graph_directive(tree).block or () if d.name == "node"
        }
        update: dict[str, Any] = {}
        for node_id in settings - replaced - added - removed:
            running = old_nodes[node_id]
            node_type = _node_spec(new_directives[node_id], tree)[0]
            if hasattr(running, "update_config") and get_node_class(node_type) is type(running):
                update[node_id] = running
        restarted = (replaced | settings) - added - removed - update.keys()
        keep = {
            node_id: node
            for node_id, node in old_nodes.items()
            if node_id not in removed | restarted | update.keys()
        }

        plan, configs = build_plan(tree, keep=keep, update=update)

        self.tree = tree
        self.plan = plan
        return PlanUpdate(
            plan=plan,
            added=tuple(sorted(added)),
            removed=tuple(sorted(removed)),
            restarted=tuple(sorted(restarted)),
            updated=configs,
            rerouted=tuple(sorted(connections - added - removed - restarted - update.keys())),
            changes=tuple(f"{change.kind} {change.address}" for change in changes),
            ignored=tuple(ignored),
        )
