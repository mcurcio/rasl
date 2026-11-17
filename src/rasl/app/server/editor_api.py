"""GraphQL for the graph editor (rasl-6sr.2, rasl-6sr.3): the config as written, and edits.

The editor reads and writes the config files, never the running graph
(``rasl.config.view``, ``rasl.config.edit``). A saved edit reaches the running graph by
the watcher's reload, as an edit in a text editor does; ``configChanged`` reports each
new version of the files and how the reload went.

Editing needs a watched config: without one (``--no-watch``) the mutations answer with
``refused`` and nothing is written. Who may call them is the front door's job (the
cluster's Keycloak sign-in, rasl-6sr.8): this server has no sign-in of its own.

A refused edit, a conflict and a config that does not build are answers, not GraphQL
errors: the editor shows them next to the edits that caused them.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import anyio
import strawberry
from strawberry.scalars import JSON
from strawberry.types import Info

from rasl.config.document import ConfigError
from rasl.config.edit import (
    AddNode,
    ConfigEditor,
    Connect,
    Detach,
    Disconnect,
    Edit,
    EditConflict,
    EditRefused,
    EditResult,
    RemoveNode,
    RemoveSetting,
    RenameNode,
    SetNodeValues,
    SetSetting,
)
from rasl.config.view import (
    ConfigView,
    NodeView,
    PortView,
    SettingView,
    describe_config,
    node_types,
    payload_types,
    preview_node,
)
from rasl.graph import ConnectError
from rasl.graph import Endpoint as GraphEndpoint

# -- types -----------------------------------------------------------------------------


@strawberry.type
class SourcePlace:
    """Where a line is written: its file and line (1-indexed)."""

    path: str
    line: int


@strawberry.type
class Port:
    """A port of a node, as ``rasl.config.view.PortView`` describes it."""

    name: str
    types: list[str]
    min_count: Optional[int]
    max_count: Optional[int]
    components: Optional[int]
    default: bool


@strawberry.type
class ConfigNode:
    """A node as written (``rasl.config.view.NodeView``).

    ``settings`` are its block's lines other than ``connect``, as key and values text.
    """

    id: str
    type: str
    place: SourcePlace
    locked: Optional[str]
    values: str
    use: Optional[str]
    settings: list["Setting"]
    inputs: list[Port]
    outputs: list[Port]
    error: Optional[str]


@strawberry.type
class Definition:
    """Where a setting's one value comes from (``rasl.config.view.Definition``):
    ``kind`` is ``variable`` (a ``@set`` line) or ``parameter`` (a ``@use`` argument)."""

    kind: str
    name: str
    values: str
    uses: int
    locked: Optional[str]


@strawberry.type
class Setting:
    """One line of a node's block (``rasl.config.view.SettingView``): its key, its
    position among the node's lines of that key, its values after variables are filled
    in and as written, and where they come from."""

    key: str
    index: int
    values: str
    written: str
    locked: Optional[str]
    definition: Optional[Definition]
    has_block: bool


@strawberry.type
class PayloadType:
    """A payload type and the types a port of it takes, as is or retyped
    (``rasl.config.view.PayloadTypeView``): what the editor's connection hints use."""

    name: str
    components: Optional[int]
    takes: list[str]


@strawberry.type
class ConfigEdge:
    """A ``connect`` line (``rasl.config.view.EdgeView``)."""

    target: str
    source: str
    port: Optional[str]
    source_node: Optional[str]
    source_port: Optional[str]
    target_port: Optional[str]
    repeat: Optional[int]
    repeat_until: Optional[int]
    place: SourcePlace
    locked: Optional[str]


@strawberry.enum
class ConnectionProblem(Enum):
    """What is wrong with a connection (``rasl.graph.ConnectProblem``)."""

    UNKNOWN_NODE = "unknown-node"
    UNKNOWN_PORT = "unknown-port"
    BAD_REFERENCE = "bad-reference"
    UNREGISTERED_TYPE = "unregistered-type"
    SLICE_RANGE = "slice-range"
    TYPE = "type"
    COUNT = "count"
    DUPLICATE = "duplicate"
    OVERLAP = "overlap"
    COMPONENTS = "components"


@strawberry.type
class Endpoint:
    """One end of a connection: node, port (null when not resolved) and slice."""

    node: str
    port: Optional[str]
    slice_start: Optional[int]
    slice_end: Optional[int]


@strawberry.type
class Connection:
    """The ports a refused connection is about (``rasl.graph.ConnectError``)."""

    problem: ConnectionProblem
    source: Endpoint
    target: Endpoint
    other: Optional[Endpoint]
    supplied: Optional[int]
    takes: Optional[int]


@strawberry.type
class ConfigProblem:
    """Why a config does not load or build, placed where it is written.

    ``connection`` is set for a connection the graph refuses.
    """

    message: str
    formatted: str
    path: Optional[str]
    line: int
    column: Optional[int]
    connection: Optional[Connection]


@strawberry.type
class ConfigGraph:
    """The graph as the config files write it (``rasl.config.view.ConfigView``).

    ``editable`` is false when the server cannot save edits (the config is not watched).
    """

    path: str
    version: str
    editable: bool
    nodes: list[ConfigNode]
    edges: list[ConfigEdge]
    error: Optional[ConfigProblem]


@strawberry.type
class NodeType:
    """A node type the palette offers: its config name, aliases, summary and settings schema."""

    name: str
    aliases: list[str]
    summary: str
    schema: Optional[JSON]


@strawberry.type
class FileChange:
    """One file an edit batch changes: its text now and after, and the unified diff."""

    path: str
    before: str
    after: str
    diff: str


@strawberry.type
class Refusal:
    """An edit that cannot be made, by its position in the batch (0-based)."""

    index: int
    message: str


@strawberry.type
class EditOutcome:
    """What a batch of edits does.

    Exactly one of: ``ok`` (it builds; ``saved`` lists the files written, empty for a
    preview), ``error`` (the edited config does not build; nothing written),
    ``refused`` (an edit cannot be made), ``conflict`` (the files changed since
    ``baseVersion``: reload the graph and make the edits again).
    """

    ok: bool
    version: str
    changes: list[FileChange]
    saved: list[str]
    error: Optional[ConfigProblem]
    refused: Optional[Refusal]
    conflict: Optional[str]


@strawberry.type
class ConfigChange:
    """A new version of the config files, and how the reload that followed went."""

    version: str
    last_reload_ok: Optional[bool]
    last_reload_error: Optional[str]


# -- inputs ----------------------------------------------------------------------------


@strawberry.input
class SettingInput:
    """One line of a new node's block: key and values as config text."""

    key: str
    values: str


@strawberry.input
class AddNodeInput:
    """``rasl.config.edit.AddNode``."""

    type: str
    id: str
    values: str = ""
    settings: list[SettingInput] = strawberry.field(default_factory=list)


@strawberry.input
class NodeRefInput:
    """``rasl.config.edit.RemoveNode``."""

    id: str


@strawberry.input
class RenameNodeInput:
    """``rasl.config.edit.RenameNode``."""

    id: str
    new_id: str


@strawberry.input
class ConnectInput:
    """``rasl.config.edit.Connect``."""

    source: str
    target: str
    port: Optional[str] = None
    repeat: Optional[int] = None
    repeat_until: Optional[int] = None


@strawberry.input
class DisconnectInput:
    """``rasl.config.edit.Disconnect``."""

    source: str
    target: str
    port: Optional[str] = None


@strawberry.input
class SetSettingInput:
    """``rasl.config.edit.SetSetting``: ``scope`` is ``line`` or ``definition``."""

    node: str
    key: str
    values: str
    index: int = 0
    scope: str = "line"


@strawberry.input
class RemoveSettingInput:
    """``rasl.config.edit.RemoveSetting``."""

    node: str
    key: str
    index: int = 0


@strawberry.input
class SetNodeValuesInput:
    """``rasl.config.edit.SetNodeValues``."""

    node: str
    values: str


@strawberry.input(one_of=True)
class EditInput:
    """One edit of a batch: exactly one field is set."""

    add_node: Optional[AddNodeInput] = strawberry.UNSET
    remove_node: Optional[NodeRefInput] = strawberry.UNSET
    rename_node: Optional[RenameNodeInput] = strawberry.UNSET
    connect: Optional[ConnectInput] = strawberry.UNSET
    disconnect: Optional[DisconnectInput] = strawberry.UNSET
    set_setting: Optional[SetSettingInput] = strawberry.UNSET
    remove_setting: Optional[RemoveSettingInput] = strawberry.UNSET
    set_node_values: Optional[SetNodeValuesInput] = strawberry.UNSET
    detach: Optional[NodeRefInput] = strawberry.UNSET


# -- conversions -----------------------------------------------------------------------


def _edit(edit: EditInput) -> Edit:
    if edit.add_node:
        a = edit.add_node
        return AddNode(a.type, a.id, a.values, tuple((s.key, s.values) for s in a.settings))
    if edit.remove_node:
        return RemoveNode(edit.remove_node.id)
    if edit.rename_node:
        return RenameNode(edit.rename_node.id, edit.rename_node.new_id)
    if edit.connect:
        c = edit.connect
        return Connect(c.source, c.target, c.port, c.repeat, c.repeat_until)
    if edit.disconnect:
        d = edit.disconnect
        return Disconnect(d.source, d.target, d.port)
    if edit.set_setting:
        s = edit.set_setting
        return SetSetting(s.node, s.key, s.values, s.index, s.scope)
    if edit.remove_setting:
        r = edit.remove_setting
        return RemoveSetting(r.node, r.key, r.index)
    if edit.set_node_values:
        return SetNodeValues(edit.set_node_values.node, edit.set_node_values.values)
    assert edit.detach  # one_of: exactly one is set
    return Detach(edit.detach.id)


def _endpoint(end: GraphEndpoint) -> Endpoint:
    return Endpoint(
        node=end.node,
        port=end.port,
        slice_start=None if end.slice is None else end.slice.start,
        slice_end=None if end.slice is None else end.slice.end,
    )


def _problem(error: ConfigError) -> ConfigProblem:
    path = None
    if error.diagnostics:
        path = str(error.diagnostics[0].place.resolved_path)
    connection = None
    caught: Any = error.connection
    if isinstance(caught, ConnectError):
        connection = Connection(
            problem=ConnectionProblem(caught.problem.value),
            source=_endpoint(caught.source),
            target=_endpoint(caught.target),
            other=None if caught.other is None else _endpoint(caught.other),
            supplied=caught.supplied,
            takes=caught.takes,
        )
    return ConfigProblem(
        message=error.message,
        formatted=str(error),
        path=path,
        line=error.line,
        column=error.column,
        connection=connection,
    )


def _port(port: PortView) -> Port:
    return Port(
        name=port.name,
        types=list(port.types),
        min_count=port.min_count,
        max_count=port.max_count,
        components=port.components,
        default=port.default,
    )


def _setting(setting: SettingView) -> Setting:
    d = setting.definition
    return Setting(
        key=setting.key,
        index=setting.index,
        values=setting.values,
        written=setting.written,
        locked=setting.locked,
        definition=None
        if d is None
        else Definition(kind=d.kind, name=d.name, values=d.values, uses=d.uses, locked=d.locked),
        has_block=setting.has_block,
    )


def _node(node: NodeView) -> ConfigNode:
    return ConfigNode(
        id=node.id,
        type=node.type,
        place=SourcePlace(path=node.place.path, line=node.place.line),
        locked=node.locked,
        values=node.values,
        use=node.use,
        settings=[_setting(setting) for setting in node.settings],
        inputs=[_port(p) for p in node.inputs],
        outputs=[_port(p) for p in node.outputs],
        error=node.error,
    )


def _graph(view: ConfigView, editable: bool) -> ConfigGraph:
    return ConfigGraph(
        path=view.path,
        version=view.version,
        editable=editable,
        nodes=[_node(n) for n in view.nodes],
        edges=[
            ConfigEdge(
                target=e.target,
                source=e.source,
                port=e.port,
                source_node=e.source_node,
                source_port=e.source_port,
                target_port=e.target_port,
                repeat=e.repeat,
                repeat_until=e.repeat_until,
                place=SourcePlace(path=e.place.path, line=e.place.line),
                locked=e.locked,
            )
            for e in view.edges
        ],
        error=None if view.error is None else _problem(view.error),
    )


def _outcome(result: EditResult) -> EditOutcome:
    return EditOutcome(
        ok=result.ok,
        version=result.version,
        changes=[
            FileChange(path=c.path, before=c.before, after=c.after, diff=c.diff())
            for c in result.changes
        ],
        saved=list(result.saved),
        error=None if result.error is None else _problem(result.error),
        refused=None,
        conflict=None,
    )


def _not_done(base_version: str, *, refused: Refusal | None = None, conflict: str | None = None) -> EditOutcome:
    return EditOutcome(
        ok=False,
        version=base_version,
        changes=[],
        saved=[],
        error=None,
        refused=refused,
        conflict=conflict,
    )


def _config_path(info: Info) -> Path | None:
    session = info.context.state.session
    return None if session is None else Path(session.path)


async def _run_edits(info: Info, base_version: str, edits: list[EditInput], save: bool) -> EditOutcome:
    path = _config_path(info)
    if path is None:
        return _not_done(
            base_version,
            refused=Refusal(index=0, message="Editing needs a watched config: rasl runs with --no-watch"),
        )
    editor = ConfigEditor(path)
    batch = [_edit(e) for e in edits]
    try:
        result = await anyio.to_thread.run_sync(
            editor.apply if save else editor.preview, batch, base_version
        )
    except EditRefused as refused:
        return _not_done(base_version, refused=Refusal(index=refused.index, message=refused.message))
    except EditConflict as conflict:
        return _not_done(base_version, conflict=str(conflict))
    except ConfigError as error:
        return EditOutcome(
            ok=False, version=base_version, changes=[], saved=[], error=_problem(error), refused=None, conflict=None
        )
    return _outcome(result)


# -- roots -----------------------------------------------------------------------------


@strawberry.type
class EditorQuery:
    """Editor queries, merged into the server's ``Query``."""

    @strawberry.field
    async def config_graph(self, info: Info) -> Optional[ConfigGraph]:
        """The graph as the config files write it; null when the server has no config
        file to read (it was started without a watched config)."""
        path = _config_path(info)
        if path is None:
            return None
        view = await anyio.to_thread.run_sync(describe_config, path)
        return _graph(view, editable=True)

    @strawberry.field
    async def node_types(self) -> list[NodeType]:
        """Every node type a ``node`` line may name, sorted by name."""
        types = await anyio.to_thread.run_sync(node_types)
        return [NodeType(name=t.name, aliases=list(t.aliases), summary=t.summary, schema=t.schema) for t in types]

    @strawberry.field
    async def payload_types(self) -> list[PayloadType]:
        """Every payload type, with the types a port of it takes (for connection hints)."""
        views = await anyio.to_thread.run_sync(payload_types)
        return [PayloadType(name=v.name, components=v.components, takes=list(v.takes)) for v in views]

    @strawberry.field
    async def preview_node(
        self, type: str, values: str = "", settings: Optional[list[SettingInput]] = None
    ) -> ConfigNode:
        """A node not in the config yet, built on its own (never started) to show its
        ports, which can depend on its settings. ``error`` says why it does not build."""
        pairs = tuple((s.key, s.values) for s in settings or [])
        try:
            view = await anyio.to_thread.run_sync(preview_node, type, values, pairs)
        except ConfigError as error:
            return ConfigNode(
                id="preview", type=type, place=SourcePlace(path="", line=0), locked=None, values=values,
                use=None, settings=[], inputs=[], outputs=[], error=error.message,
            )
        return _node(view)


@strawberry.type
class EditorMutation:
    """Editor mutations: check a batch of edits, or save it."""

    @strawberry.mutation
    async def preview_edits(self, info: Info, base_version: str, edits: list[EditInput]) -> EditOutcome:
        """What ``edits`` would change, and whether the result builds; writes nothing."""
        return await _run_edits(info, base_version, edits, save=False)

    @strawberry.mutation
    async def apply_edits(self, info: Info, base_version: str, edits: list[EditInput]) -> EditOutcome:
        """Apply ``edits`` and save the files when the result builds. The watcher then
        reloads them; ``configChanged`` reports how that went."""
        return await _run_edits(info, base_version, edits, save=True)


@strawberry.type
class EditorSubscription:
    """Editor subscriptions, merged into the server's ``Subscription``."""

    @strawberry.subscription
    async def config_changed(
        self, info: Info, interval_ms: int = 1000
    ) -> AsyncGenerator[ConfigChange, None]:
        """The files' version now, then each time it, or the last reload's outcome,
        changes (checked every ``interval_ms``, at least 200). Nothing when the config
        is not watched."""
        path = _config_path(info)
        if path is None:
            return
        session = info.context.state.session
        last: tuple[str, Any] | None = None
        editor = ConfigEditor(path)
        while True:
            try:
                version = await anyio.to_thread.run_sync(editor.version)
            except (ConfigError, FileNotFoundError, OSError):
                version = ""
            reload = session.last_reload
            current = (version, reload)
            if current != last:
                last = current
                yield ConfigChange(
                    version=version,
                    last_reload_ok=None if reload is None else reload.ok,
                    last_reload_error=None if reload is None else reload.error,
                )
            await anyio.sleep(max(interval_ms, 200) / 1000)
