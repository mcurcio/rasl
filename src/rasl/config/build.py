"""Building an ExecutionPlan from a rendered config.

- the ``graph`` block holds the nodes
- each ``node`` directive becomes a node (``rasl.config.node_directive``)
- each ``connect`` directive in a node's block becomes edges, resolved
  against the ports the nodes declare (``rasl.config.connect``)
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rasl.config.connect import parse_connect_directive, resolve_connections
from rasl.config.document import (
    ConfigError,
    Directive,
    Rendered,
    children,
    config_error,
    load_document,
    parse_document,
)
from rasl.config.node_directive import _node_config, node_spec
from rasl.graph import ConnectError, ExecutionPlan, GraphBuilder, PortTypeError
from rasl.graph.node import ensure_nodes_loaded
from rasl.runtime import pull_rate_of


def graph_directive(tree: Rendered) -> Directive:
    """The config's ``graph`` block.

    Raises:
        ConfigError: If there is none.
    """
    graph_directives = tree.block.directives("graph")
    if not graph_directives:
        raise config_error(
            tree, "No 'graph' block found in configuration", code="rasl/no-graph", tree=tree
        )
    return graph_directives[0]


def build_plan(
    tree: Rendered,
    *,
    keep: Mapping[str, Any] | None = None,
    update: Mapping[str, Any] | None = None,
) -> tuple[ExecutionPlan, dict[str, Any]]:
    """Build an ExecutionPlan from a rendered config, reusing running nodes.

    A reload passes the node objects that go on running: the plan holds those
    same objects, with their connections read again from the config.

    Args:
        tree: The rendered config.
        keep: Running nodes, by id, whose own settings did not change. They are
            reused as they are; their config is not read.
        update: Running nodes, by id, whose settings changed and that take a new
            config in place (``update_config``). They are reused, and the new
            validated config of each is returned for the caller to apply.

    Returns:
        (plan, the new config of each node in ``update``, by id).

    Raises:
        ConfigError: If the config is invalid. Reused nodes are left as they were.
    """
    ensure_nodes_loaded()
    keep = keep or {}
    update = update or {}

    builder = GraphBuilder()
    node_directives: dict[str, Directive] = {}
    configs: dict[str, Any] = {}

    # First pass: build all nodes
    for directive in children(graph_directive(tree), "node"):
        node_type, node_id = node_spec(directive, tree)
        if node_id in keep:
            node = keep[node_id]
        else:
            node_class, config = _node_config(node_type, node_id, directive, tree)
            if node_id in update:
                node = update[node_id]
                configs[node_id] = config
            else:
                node = node_class(config)
        builder.add_node(node)
        node_directives[node_id] = directive

    # Second pass: each node's connect directives become edges, now that every
    # node (and so every port) is known. An error is placed on the connect line
    # that asks for the connection, and carries the graph's ConnectError.
    edge_lines: list[tuple[int, Directive]] = []  # (first edge index, connect line)
    for node_id, directive in node_directives.items():
        for line in children(directive, "connect"):
            try:
                descriptor = parse_connect_directive(line)
                edge_lines.append((len(builder.edges), line))
                resolve_connections(builder, node_id, [descriptor])
            except (KeyError, ValueError, TypeError) as e:
                raise _connect_error(line, node_id, e, tree) from e

    try:
        plan = builder.build()
    except PortTypeError as e:
        # A pass-through output's type is known only once every edge is: placed on
        # the connect line that made the edge
        index = builder.edges.index(e.edge)
        line = next(line for first, line in reversed(edge_lines) if first <= index)
        raise _connect_error(line, e.node, e, tree) from e
    # A node's rate comes from its settings: check it here, on the node's line
    for node_id, node in plan.nodes.items():
        try:
            pull_rate_of(node_id, node, plan.wiring(node_id))
        except ValueError as e:
            raise config_error(
                node_directives[node_id], str(e), code="rasl/rate", tree=tree
            ) from e
    return plan, configs


def _connect_error(line: Directive, node_id: str, error: Exception, tree: Rendered) -> ConfigError:
    """A connect line's error, placed on that line, with the graph's ``ConnectError``."""
    message = error.args[0] if isinstance(error, KeyError) and error.args else str(error)
    return config_error(
        line,
        f"Node '{node_id}': {message}",
        code="rasl/connect",
        tree=tree,
        connection=error if isinstance(error, ConnectError) else None,
    )


def parse_config(config_text: str) -> ExecutionPlan:
    """Parse config text and build an ExecutionPlan.

    Args:
        config_text: Configuration in knobly syntax.

    Returns:
        Compiled ExecutionPlan ready for Runtime.

    Raises:
        ConfigError: If parsing fails or config is invalid.
    """
    return build_plan(parse_document(config_text))[0]


def load_config(config_path: str | Path) -> ExecutionPlan:
    """Load config from file and build an ExecutionPlan.

    Args:
        config_path: Path to the configuration file.

    Returns:
        Compiled ExecutionPlan ready for Runtime.

    Raises:
        ConfigError: If loading or parsing fails.
        FileNotFoundError: If config file doesn't exist.
    """
    return build_plan(load_document(config_path))[0]
