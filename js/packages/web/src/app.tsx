// The rasl web UI: the graph as the config files write it, live health, and the editor.
// Edits queue (drawn dashed until saved), are checked against the server as they are made,
// and are written to the files only on Save; the watcher then reloads the running graph.
import { Banner, CommandPalette, type PalettePoint } from "@mcurcio/patchbay/composites";
import {
  ariaKeyShortcuts,
  keyLabel,
  type Shortcut,
  useMediaBreakpoint,
  usePersistentState,
  useShortcuts,
  useTheme,
} from "@mcurcio/patchbay/hooks";
import {
  type CanConnect,
  CanvasTools,
  ConnectHints,
  mergeFlowProps,
  type OnAddAt,
  type PortRef,
  useAddAt,
  useConnectHints,
  useFollowFit,
  Wire,
  type WireEdge,
  type WireTone,
} from "@mcurcio/patchbay/graph";
import { Button, Pill, ThemeSwitch } from "@mcurcio/patchbay/primitives";
import { AppShell, clampInspectorWidth } from "@mcurcio/patchbay/shell";
import {
  Background,
  type Connection,
  type FitViewOptions,
  type Node,
  type NodeChange,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useUpdateNodeInternals,
} from "@xyflow/react";
import { type ReactElement, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  applyEdits,
  type ConfigGraph,
  type ConfigNode,
  type Edit,
  type EditOutcome,
  fetchConfigGraph,
  fetchNodeTypes,
  fetchPayloadTypes,
  type NodeMetrics,
  type NodeType,
  type PayloadType,
  previewEdits,
  subscribe,
} from "./api";
import { AddNodeDialog, type AddNodeRequest } from "./components/add-node-dialog";
import { Inspector } from "./components/inspector";
import { NodeCard, type NodeCardData } from "./components/node-card";
import { PendingPanel } from "./components/pending-panel";
import { layout, type Positions } from "./layout";
import { typeCommands } from "./palette";
import { THEME_KEY } from "./theme";
import { accepts, connectEdit, queue, stage, type StagedGraph, type ViewEdge, type ViewNode } from "./model";

const NODE_TYPES = { card: NodeCard };
const EDGE_TYPES = { wire: Wire };

/** A connection's tone on its Wire: a queued change in the change's tone, one the graph refuses in the refused one. */
const EDGE_TONES: Readonly<Record<ViewEdge["status"], WireTone | undefined>> = {
  saved: undefined,
  added: "added",
  removed: "removed",
  renamed: "changed",
  changed: "changed",
};

/** How every fit frames the graph: patchbay's useFollowFit after each layout, and CanvasTools' fit tool. */
const FIT: FitViewOptions = { padding: 0.12 };

/** The key that opens the add-node palette. */
const ADD_KEYS = "Mod+K";

/** The side column's width in px where nothing is kept; AppShell holds it to 280-560 px. */
const SIDE_WIDTH = 360;

/** Where the side column's width and, on a wide window, whether it is shown are kept (patchbay's usePersistentState). */
const SIDE_KEYS = { width: "rasl-web/1/side-width", open: "rasl-web/1/side-open" } as const;

/** The side column's name, as AppShell's inspector region and narrow window's sheet, and its splitter's. */
const SIDE_LABELS = { inspector: "Side panel", resizeInspector: "Resize the side panel" } as const;

const keptWidth = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) ? clampInspectorWidth(value) : undefined;
const keptOpen = (value: unknown): boolean | undefined => (typeof value === "boolean" ? value : undefined);

type Selection = { readonly node?: string; readonly edge?: string };

/**
 * Adding a node: first its type is picked in patchbay's CommandPalette (anchored where the pane was double-clicked or
 * a wire dropped, else centred), then the add-node dialog takes its id and settings.
 */
type Adding = {
  /** Set when a dropped wire opened it: the new node is connected to it. */
  readonly from: { readonly node: string; readonly port: string } | null;
  readonly at?: PalettePoint;
  /** The type picked; null while the palette is open. */
  readonly type: NodeType | null;
  /**
   * Back from the dialog: the palette opens once the dialog has given the focus back to what opened it (in its
   * effect's cleanup), so the palette returns it there too and keeps the focus it takes.
   */
  readonly back?: boolean;
};

function portOf(node: ViewNode | undefined, handle: string | null): ViewNode["inputs"][number] | undefined {
  if (!node || handle === null) return undefined;
  const [side, name] = [handle.slice(0, handle.indexOf(":")), handle.slice(handle.indexOf(":") + 1)];
  return (side === "in" ? node.inputs : node.outputs).find((p) => p.name === name);
}

/** The ports a refused connection names, by node and handle, with the refusal's words. */
function problemPorts(outcome: EditOutcome | null): ReadonlyMap<string, ReadonlyMap<string, string>> {
  const ports = new Map<string, Map<string, string>>();
  const error = outcome?.error;
  const connection = error?.connection;
  if (!error || !connection) return ports;
  const add = (node: string, handle: string): void => {
    ports.set(node, (ports.get(node) ?? new Map<string, string>()).set(handle, error.message));
  };
  if (connection.source.port) add(connection.source.node, `out:${connection.source.port}`);
  if (connection.target.port) add(connection.target.node, `in:${connection.target.port}`);
  return ports;
}

function Editor(): ReactElement {
  const [graph, setGraph] = useState<ConfigGraph | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [types, setTypes] = useState<readonly NodeType[]>([]);
  const [payloadTypes, setPayloadTypes] = useState<ReadonlyMap<string, PayloadType>>(new Map());
  const [edits, setEdits] = useState<readonly Edit[]>([]);
  const [previews, setPreviews] = useState<ReadonlyMap<string, ConfigNode>>(new Map());
  const [outcome, setOutcome] = useState<EditOutcome | null>(null);
  const [busy, setBusy] = useState<"check" | "save" | null>(null);
  const [sideWidth, setSideWidth] = usePersistentState<number>(SIDE_KEYS.width, SIDE_WIDTH, keptWidth);
  const [stale, setStale] = useState(false);
  const [metrics, setMetrics] = useState<ReadonlyMap<string, NodeMetrics>>(new Map());
  const [connected, setConnected] = useState(false);
  const [reloadError, setReloadError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>({});
  const [dialog, setDialog] = useState<Adding | null>(null);
  const [positions, setPositions] = useState<Positions>(new Map());
  // The graph shape the view was last laid out (and, while the view follows the layout, fitted) for: the canvas says
  // data-layout="ready" when it matches the shape now shown (tests wait for it)
  const [fittedShape, setFittedShape] = useState<string | null>(null);
  const positionsShape = useRef<string | null>(null);
  // Each node's measured size, as React Flow reports it. The nodes are rebuilt from the
  // graph on every render, so the size is passed back with them: without it React Flow
  // keeps a rebuilt node hidden until it measures it again, which it may never do.
  const [measured, setMeasured] = useState<ReadonlyMap<string, { width: number; height: number }>>(new Map());
  const onNodesChange = useCallback((changes: NodeChange[]): void => {
    const sizes = changes.flatMap((c) =>
      c.type === "dimensions" && c.dimensions ? [[c.id, c.dimensions] as const] : [],
    );
    if (sizes.length === 0) return;
    setMeasured((current) => {
      const next = new Map(current);
      for (const [id, size] of sizes) next.set(id, size);
      return next;
    });
  }, []);
  // A rebuilt node that reaches React Flow before its size is passed back loses its handles' bounds, and React Flow
  // may not measure it again (its size has not changed), so a wire could not be dragged from it: once the sizes are
  // passed back, the handles are measured again. (NodeBox measures them again only when its ports change.)
  const updateNodeInternals = useUpdateNodeInternals();
  useEffect(() => {
    if (measured.size > 0) updateNodeInternals([...measured.keys()]);
  }, [measured, updateNodeInternals]);
  const [saved, setSaved] = useState<readonly string[]>([]);
  const [theme, setTheme] = useTheme({ key: THEME_KEY });
  // The side column is AppShell's inspector. On a wide window it is shown beside the canvas until the top bar's button
  // hides it, which is kept. Below 760 px AppShell draws it as a Sheet over the canvas (from its bottom below 600 px),
  // which starts closed: a press on the canvas, its close button or Escape inside it close it. At every width a
  // selection shows it and the top bar's button toggles it.
  const narrow = useMediaBreakpoint().width !== "wide";
  const [wideOpen, setWideOpen] = usePersistentState<boolean>(SIDE_KEYS.open, true, keptOpen);
  const [sheetOpen, setSheetOpen] = useState(false);
  const sideOpen = narrow ? sheetOpen : wideOpen;
  const setSideOpen = narrow ? setSheetOpen : setWideOpen;
  useEffect(() => {
    if (selection.node !== undefined || selection.edge !== undefined) setSideOpen(true);
  }, [selection]);
  const flow = useReactFlow();
  const versionRef = useRef<string | null>(null);
  const editsRef = useRef(edits);
  editsRef.current = edits;

  const load = useCallback(async (): Promise<void> => {
    try {
      const fresh = await fetchConfigGraph();
      setLoadError(fresh === null ? "This server has no watched config: start rasl without --no-watch to edit." : null);
      if (fresh) {
        if (versionRef.current !== null && versionRef.current !== fresh.version && editsRef.current.length > 0)
          setStale(true);
        versionRef.current = fresh.version;
      }
      setGraph(fresh);
    } catch (error) {
      setLoadError(String(error));
    }
  }, []);

  useEffect(() => {
    void load();
    fetchNodeTypes().then(setTypes, (e: unknown) => setLoadError(String(e)));
    fetchPayloadTypes().then(
      (list) => setPayloadTypes(new Map(list.map((t) => [t.name, t]))),
      (e: unknown) => setLoadError(String(e)),
    );
    return subscribe({
      onConfigChange: (version, ok, error) => {
        setReloadError(ok === false ? error : null);
        if (version !== versionRef.current) void load();
      },
      onMetrics: (nodes) => setMetrics(new Map(nodes.map((m) => [m.nodeId, m]))),
      onConnection: setConnected,
    });
  }, [load]);

  const staged: StagedGraph | null = useMemo(
    () => (graph ? stage(graph, edits, previews) : null),
    [graph, edits, previews],
  );

  // Layout follows the structure only, so a metrics tick does not move anything
  const shape = staged
    ? JSON.stringify([
        staged.nodes.map((n) => [n.id, n.inputs.length, n.outputs.length]),
        staged.edges.map((e) => e.key),
      ])
    : "";
  useEffect(() => {
    if (!staged) return;
    let current = true;
    layout(staged).then(
      (p) => {
        if (!current) return;
        positionsShape.current = shape;
        setPositions(p);
      },
      () => undefined,
    );
    return () => {
      current = false;
    };
  }, [shape]);

  // Fit the view to each new layout once it is drawn and measured, until the person moves the view (patchbay's
  // useFollowFit; CanvasTools' fit tool follows again). Each fit that lands says the layout is ready; while the view
  // does not follow, a layout is ready once it is placed, as nothing will move the view.
  const follow = useFollowFit({
    key: positions,
    fitOptions: FIT,
    onFitted: () => setFittedShape(positionsShape.current),
  });
  useEffect(() => {
    if (!follow.following && positions.size > 0) setFittedShape(positionsShape.current);
  }, [positions, follow.following]);

  // Check the queue against the server as it changes: the diff, and whether it builds
  useEffect(() => {
    setOutcome(null);
    if (!graph || edits.length === 0) return;
    const timer = window.setTimeout(() => {
      previewEdits(graph.version, edits).then(setOutcome, (e: unknown) => setLoadError(String(e)));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [graph, edits]);

  const push = useCallback((edit: Edit) => {
    setSaved([]);
    setEdits((current) => queue(current, edit));
  }, []);

  const check = useCallback(async (): Promise<void> => {
    if (!graph) return;
    setBusy("check");
    try {
      setOutcome(await previewEdits(graph.version, edits));
      setStale(false);
    } finally {
      setBusy(null);
    }
  }, [graph, edits]);

  const save = useCallback(async (): Promise<void> => {
    if (!graph) return;
    setBusy("save");
    try {
      const result = await applyEdits(graph.version, edits);
      setOutcome(result);
      if (result.ok) {
        setEdits([]);
        setPreviews(new Map());
        setStale(false);
        setSaved(result.saved);
        await load();
      } else if (result.conflict) {
        setStale(true);
        await load();
      }
    } finally {
      setBusy(null);
    }
  }, [graph, edits, load]);

  const addNode = useCallback(
    (request: AddNodeRequest): void => {
      const from = dialog?.from ?? null;
      setPreviews((current) => new Map(current).set(request.id, request.preview));
      push({ addNode: { type: request.type, id: request.id, values: request.values, settings: request.settings } });
      if (from && staged) {
        const source = staged.nodes.find((n) => n.id === from.node);
        const input = request.preview.inputs.find((p) => p.default) ?? request.preview.inputs[0];
        if (source && input) {
          const target = {
            ...source,
            id: request.id,
            inputs: request.preview.inputs,
            outputs: request.preview.outputs,
          };
          push(connectEdit(source, from.port, target, input.name));
        }
      }
      setSelection({ node: request.id });
      setDialog(null);
    },
    [dialog, push, staged],
  );

  const onConnect = useCallback(
    (connection: Connection): void => {
      if (!staged || !connection.sourceHandle || !connection.targetHandle) return;
      const from = staged.nodes.find((n) => n.id === connection.source);
      const to = staged.nodes.find((n) => n.id === connection.target);
      if (!from || !to) return;
      push(
        connectEdit(
          from,
          connection.sourceHandle.replace(/^out:/, ""),
          to,
          connection.targetHandle.replace(/^in:/, ""),
        ),
      );
    },
    [staged, push],
  );

  // A double-click on empty canvas, or a wire from an output dropped there, opens the palette at that point; the wire's
  // output is then joined to the new node. A wire from an input dropped there adds nothing.
  const onAddAt: OnAddAt = (point, from) => {
    if (from !== undefined && (from.side !== "output" || from.handleId === null)) return;
    setDialog({
      from: from ? { node: from.nodeId, port: (from.handleId ?? "").replace(/^out:/, "") } : null,
      at: flow.flowToScreenPosition(point),
      type: null,
    });
  };
  const addAt = useAddAt(onAddAt, { enabled: graph?.editable === true });

  const removeSelection = useCallback((): void => {
    if (!staged) return;
    if (selection.edge) {
      const edge = staged.edges.find((e) => e.key === selection.edge);
      if (edge && edge.status !== "removed" && !edge.locked)
        push({ disconnect: { source: edge.source, target: edge.target, port: edge.port } });
    } else if (selection.node) {
      const node = staged.nodes.find((n) => n.id === selection.node);
      if (node && node.status !== "removed" && !node.locked) push({ removeNode: { id: node.id } });
    }
    setSelection({});
  }, [staged, selection, push]);

  // The editor's keys, on patchbay's useShortcuts: idle while the add-node dialog is open. Single keys never act
  // while a text field has the focus; Mod is Cmd on Apple platforms and Ctrl elsewhere.
  const shortcuts: readonly Shortcut[] = [
    { keys: ["Delete", "Backspace"], run: removeSelection },
    { keys: "Mod+Z", run: () => setEdits((current) => current.slice(0, -1)) },
    // A palette's chord: it acts in a text field too
    { keys: ADD_KEYS, run: () => setDialog({ from: null, type: null }), inTextFields: true },
  ];
  useShortcuts(shortcuts, { enabled: dialog === null });

  useEffect(() => {
    if (dialog?.back) setDialog({ ...dialog, back: false });
  }, [dialog]);

  // The palette asks to close before a command runs, so each command sets the step from the palette's own state
  const commands = useMemo(
    () => typeCommands(types, (type) => setDialog(dialog && { ...dialog, type })),
    [types, dialog],
  );

  const problems = useMemo(() => problemPorts(outcome), [outcome]);
  // One rule for the hints a dragged wire shows and for React Flow's check on the drop: the output's payload must be
  // one the input takes (model.ts accepts()), and a node is never wired to itself
  const canConnect: CanConnect = (from: PortRef, to: PortRef): boolean => {
    if (from.nodeId === to.nodeId) return false;
    const output = portOf(
      staged?.nodes.find((n) => n.id === from.nodeId),
      from.handleId,
    );
    const input = portOf(
      staged?.nodes.find((n) => n.id === to.nodeId),
      to.handleId,
    );
    return output === undefined || input === undefined || accepts(output, input, payloadTypes);
  };
  const hints = useConnectHints(canConnect);

  const flowNodes: Node[] = useMemo(
    () =>
      (staged?.nodes ?? []).map((node) => ({
        id: node.id,
        type: "card",
        position: positions.get(node.id) ?? { x: 0, y: 0 },
        measured: measured.get(node.id),
        selected: selection.node === node.id,
        draggable: false,
        connectable: graph?.editable === true && node.status !== "removed",
        data: {
          node,
          metrics: metrics.get(node.renamedFrom ?? node.id),
          problemPorts: problems.get(node.id) ?? new Map(),
        } satisfies NodeCardData,
      })),
    [staged, positions, measured, selection, metrics, problems, graph],
  );

  const flowEdges: WireEdge[] = useMemo(() => {
    const connection = outcome?.error?.connection;
    return (staged?.edges ?? [])
      .filter((e) => e.sourceNode !== null)
      .map((e: ViewEdge) => {
        const failing =
          connection !== undefined &&
          connection !== null &&
          connection.target.node === e.target &&
          connection.source.node === e.sourceNode;
        return {
          id: e.key,
          source: e.sourceNode as string,
          target: e.target,
          sourceHandle: e.sourcePort ? `out:${e.sourcePort}` : null,
          targetHandle: e.targetPort ? `in:${e.targetPort}` : null,
          selected: selection.edge === e.key,
          type: "wire",
          data: {
            tone: failing ? "refused" : EDGE_TONES[e.status],
            dashed: e.status !== "saved",
            arrow: true,
            label: e.repeat ? `×${e.repeat}` : e.repeatUntil ? `→${e.repeatUntil}` : undefined,
            title: failing ? outcome?.error?.message : undefined,
          },
        } satisfies WireEdge;
      });
  }, [staged, selection, outcome]);

  const selectedNode = staged?.nodes.find((n) => n.id === selection.node) ?? null;
  const selectedEdge = staged?.edges.find((e) => e.key === selection.edge) ?? null;
  const editable = graph?.editable === true;

  // The side column's content: docked beside the canvas, or in the narrow window's sheet
  const side = (
    <div className="side">
      <Inspector
        node={selectedNode}
        edge={selectedEdge}
        metrics={selectedNode ? metrics.get(selectedNode.renamedFrom ?? selectedNode.id) : undefined}
        editable={editable}
        onRename={(id, newId) => push({ renameNode: { id, newId } })}
        onRemove={(id) => push({ removeNode: { id } })}
        onDisconnect={(edge) => push({ disconnect: { source: edge.source, target: edge.target, port: edge.port } })}
        schema={
          types.find((t) => t.name === selectedNode?.type || t.aliases.includes(selectedNode?.type ?? ""))?.schema ??
          null
        }
        onSetSetting={(key, index, values, scope) => {
          if (selectedNode) push({ setSetting: { node: selectedNode.id, key, index, values, scope } });
        }}
        onRemoveSetting={(key, index) => {
          if (selectedNode) push({ removeSetting: { node: selectedNode.id, key, index } });
        }}
        onSetValues={(values) => {
          if (selectedNode) push({ setNodeValues: { node: selectedNode.id, values } });
        }}
        onDetach={() => {
          if (selectedNode) push({ detach: { id: selectedNode.id } });
        }}
      />
      {editable ? (
        <PendingPanel
          edits={edits}
          outcome={outcome}
          saved={saved}
          busy={busy}
          stale={stale}
          onDrop={(index) => setEdits((current) => current.filter((_, i) => i !== index))}
          onCheck={() => void check()}
          onSave={() => void save()}
          onDiscard={() => {
            setEdits([]);
            setPreviews(new Map());
            setStale(false);
          }}
        />
      ) : null}
    </div>
  );

  return (
    <>
      <AppShell
        topBar={{
          brand: "rasl",
          status: (
            <Pill
              tone={connected ? "ok" : "err"}
              label={connected ? "live" : "offline"}
              title={connected ? "Receiving live updates from rasl" : "Not connected to rasl's live updates"}
            />
          ),
          start: (
            <>
              {editable ? (
                <Button
                  aria-keyshortcuts={ariaKeyShortcuts(ADD_KEYS)}
                  onClick={() => setDialog({ from: null, type: null })}
                >
                  Add node ({keyLabel(ADD_KEYS)})
                </Button>
              ) : null}
              <Button aria-expanded={sideOpen} onClick={() => setSideOpen(!sideOpen)}>
                Side panel
              </Button>
              <span className="path muted mono small">{graph?.path}</span>
            </>
          ),
          end: <ThemeSwitch choice={theme} onChoose={setTheme} />,
        }}
        inspector={{ content: side, open: sideOpen, onOpen: setSideOpen, width: sideWidth, onWidth: setSideWidth }}
        labels={SIDE_LABELS}
      >
        <div className="workspace">
          {loadError || reloadError || (graph?.error && edits.length === 0) ? (
            <div className="banners">
              {loadError ? <Banner tone="err">{loadError}</Banner> : null}
              {reloadError ? <Banner tone="err">The running graph did not reload: {reloadError}</Banner> : null}
              {graph?.error && edits.length === 0 ? (
                <Banner tone="warn">The config does not build: {graph.error.message}</Banner>
              ) : null}
            </div>
          ) : null}
          <section className="canvas" data-layout={staged && fittedShape === shape ? "ready" : "pending"}>
            <ConnectHints value={hints.value}>
              <ReactFlow
                {...mergeFlowProps(hints.flowProps, addAt.flowProps, follow.flowProps)}
                nodes={flowNodes}
                edges={flowEdges}
                nodeTypes={NODE_TYPES}
                edgeTypes={EDGE_TYPES}
                onConnect={onConnect}
                onNodesChange={onNodesChange}
                onNodeClick={(_, node) => setSelection({ node: node.id })}
                onEdgeClick={(_, edge) => setSelection({ edge: edge.id })}
                onPaneClick={() => {
                  setSelection({});
                  setSheetOpen(false);
                }}
                nodesConnectable={editable}
                deleteKeyCode={null}
                proOptions={{ hideAttribution: true }}
              >
                <Background />
                <CanvasTools onFit={follow.fit} fitOptions={FIT} />
              </ReactFlow>
            </ConnectHints>
          </section>
        </div>
      </AppShell>
      <CommandPalette
        open={dialog !== null && dialog.type === null && dialog.back !== true}
        onClose={() => setDialog(null)}
        commands={commands}
        at={dialog?.at}
        labels={{
          palette: "Add a node",
          placeholder: "Search node types",
          empty: "No node types",
          noMatch: (query) => `No node type matches “${query}”`,
        }}
      />
      {dialog?.type && staged ? (
        <AddNodeDialog
          key={dialog.type.name}
          type={dialog.type}
          takenIds={new Set(staged.nodes.map((n) => n.id))}
          from={dialog.from}
          onAdd={addNode}
          onBack={() => setDialog({ ...dialog, type: null, back: true })}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </>
  );
}

export function App(): ReactElement {
  return (
    <ReactFlowProvider>
      <Editor />
    </ReactFlowProvider>
  );
}
