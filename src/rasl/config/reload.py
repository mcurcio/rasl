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

``reload()`` only works the update out. The session goes on describing what is
running until the caller, having applied the update, says so with ``commit()``.

Example:
    >>> session = ConfigSession("config.conf")
    >>> runtime = Runtime(session.plan)
    >>> # ... later, after config.conf was edited:
    >>> update = session.reload()
    >>> if update is not None:
    ...     await runtime.request_update(update).wait()
    ...     if runtime.plan is update.plan:
    ...         session.commit(update)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rasl.config.build import build_plan, graph_directive
from rasl.config.document import ConfigError, Directive, Rendered, children, load_document
from rasl.config.node_directive import node_id_of, node_spec
from rasl.config.settings import RuntimeSettings, UiSettings, runtime_settings, ui_settings
from rasl.graph import ExecutionPlan
from rasl.graph.node import get_node_class
from rasl.runtime.plan_update import PlanUpdate

_CONNECTION_KEYWORDS = ("connect", "edge")
"""The lines in a node's block that describe routing, not the node's settings."""


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


@dataclass(frozen=True)
class ReloadOutcome:
    """How the last attempt to reload the config ended.

    Attributes:
        ok: True if the config was reloaded and what changed now runs (or nothing a
            program reads had changed); False if the reload failed and the graph
            kept running as it was.
        at: When the attempt ended, in Unix seconds.
        error: Why it failed, as a message; None when ``ok``.
    """

    ok: bool
    at: float
    error: str | None = None


class ConfigSession:
    """A config file as last loaded, and the plan built from it.

    Attributes:
        path: The root config file.
        tree: The render of it that is running (knobly's rendered tree).
        plan: The plan built from that render.
        last_reload: How the last reload attempt ended, set by whatever reloads the
            session (``watch_config``); None until one is attempted.
        ui: The ``ui`` block's settings, as loaded (a change takes a restart).
        runtime: The ``runtime`` block's settings, as loaded (a change takes a restart).
    """

    def __init__(self, path: str | Path) -> None:
        """Load the config and build its plan.

        Raises:
            ConfigError: If the config is invalid.
            FileNotFoundError: If the file doesn't exist.
        """
        self.path = Path(path)
        self.tree: Rendered = load_document(self.path)
        self.ui: UiSettings = ui_settings(self.tree)
        self.runtime: RuntimeSettings = runtime_settings(self.tree)
        self.plan: ExecutionPlan = build_plan(self.tree)[0]
        self._attempted: tuple[str, ...] = ()
        self.last_reload: ReloadOutcome | None = None

    @property
    def documents(self) -> tuple[str, ...]:
        """Every file of the running config: the root and the files it includes."""
        return tuple(self.tree.graph.documents)

    @property
    def watched(self) -> tuple[str, ...]:
        """The files whose change calls for a reload: the running config's, and
        those the last ``reload()`` read, which may include new or broken files
        that the running config does not."""
        return tuple(dict.fromkeys((*self.documents, *self._attempted)))

    def commit(self, update: PlanUpdate) -> None:
        """Record that ``update`` is now what runs.

        Call it once the runtime has applied the update. Until then the session
        describes the old config, so an update that was never applied is worked
        out again by the next ``reload()``.
        """
        self.tree = update.tree
        self.plan = update.plan

    def reload(self) -> PlanUpdate | None:
        """Load the files again and work out how the plan changes.

        The session itself is not changed (see ``commit``).

        Returns:
            The update to hand to the runtime, or None when nothing a program
            reads changed (a comment, the layout, a quote style).

        Raises:
            ConfigError: If the config is now invalid.
            Exception: Whatever else building the new plan raises (an unknown
                node in a ``connect``, a duplicate id, ...). In every case the
                session, the plan and the running nodes are left as they were.
        """
        try:
            tree = load_document(self.path)
        except ConfigError as error:
            self._attempted = error.documents
            raise
        self._attempted = tuple(tree.graph.documents)
        # A bad settings block fails the reload, so the edit is reported now; the
        # settings themselves apply at the next restart
        ui_settings(tree)
        runtime_settings(tree)
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

        if not (added or removed or replaced or settings or connections):
            # Nothing a node reads changed: the running plan stands
            return PlanUpdate(
                plan=self.plan,
                tree=tree,
                changes=tuple(f"{change.kind} {change.address}" for change in changes),
                ignored=tuple(ignored),
            )

        new_directives = {node_id_of(d): d for d in children(graph_directive(tree), "node")}
        update: dict[str, Any] = {}
        for node_id in settings - replaced - added - removed:
            running = old_nodes[node_id]
            node_type = node_spec(new_directives[node_id], tree)[0]
            if hasattr(running, "update_config") and get_node_class(node_type) is type(running):
                update[node_id] = running
        restarted = (replaced | settings) - added - removed - update.keys()
        keep = {
            node_id: node
            for node_id, node in old_nodes.items()
            if node_id not in removed | restarted | update.keys()
        }

        plan, configs = build_plan(tree, keep=keep, update=update)

        return PlanUpdate(
            plan=plan,
            tree=tree,
            added=tuple(sorted(added)),
            removed=tuple(sorted(removed)),
            restarted=tuple(sorted(restarted)),
            updated=configs,
            rerouted=tuple(sorted(connections - added - removed - restarted - update.keys())),
            changes=tuple(f"{change.kind} {change.address}" for change in changes),
            ignored=tuple(ignored),
        )
