"""A plan update: what the runtime is handed to change the running graph."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from rasl.graph import ExecutionPlan


@dataclass(frozen=True)
class PlanUpdate:
    """A new plan, and how it differs from the one running.

    Node ids appear in at most one of ``added``, ``removed``, ``restarted``,
    ``updated`` and ``rerouted``.

    Attributes:
        plan: The new plan. Nodes that keep running are the same objects as in
            the old plan. The running plan itself when no node changes.
        tree: What the plan was built from, for whoever made the update to
            record once it is applied (the config's rendered tree; the runtime
            does not read it).
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
    tree: Any
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    restarted: tuple[str, ...] = ()
    updated: Mapping[str, Any] = field(default_factory=dict)
    rerouted: tuple[str, ...] = ()
    changes: tuple[str, ...] = ()
    ignored: tuple[str, ...] = ()

    @property
    def changes_graph(self) -> bool:
        """False when every change is in ``ignored``: there is nothing to swap."""
        return bool(self.added or self.removed or self.restarted or self.updated or self.rerouted)
