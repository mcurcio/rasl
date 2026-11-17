// The rasl web UI: the graph as the config files write it, live health, and the editor.
// Edits queue (drawn dashed until saved), are checked against the server as they are made,
// and are written to the files only on Save; the watcher then reloads the running graph.
import {
  Background,
  type Connection,
  Controls,
  type Edge,
  type FinalConnectionState,
  MarkerType,
  type Node,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import { type MouseEvent, type ReactElement, useCallback, useEffect, useMemo, useRef, useState } from "react";

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
import { accepts, connectEdit, queue, stage, type StagedGraph, type ViewEdge, type ViewNode } from "./model";

const NODE_TYPES = { card: NodeCard };

type Selection = { readonly node?: string; readonly edge?: string };

/** The end a wire is being dragged from. */
type Dragging = { readonly node: string; readonly handle: string; readonly side: "source" | "target" };

function portOf(node: ViewNode | undefined, handle: string): ViewNode["inputs"][number] | undefined {
  if (!node) return undefined;
  const [side, name] = [handle.slice(0, handle.indexOf(":")), handle.slice(handle.indexOf(":") + 1)];
  return (side === "in" ? node.inputs : node.outputs).find((p) => p.name === name);
}

/** For a dragged wire, whether each handle on the other side takes it, by node. */
function connectionHints(
  graph: StagedGraph,
  dragging: Dragging,
  types: ReadonlyMap<string, PayloadType>,
): ReadonlyMap<string, ReadonlyMap<string, boolean>> {
  const from = portOf(
    graph.nodes.find((n) => n.id === dragging.node),
    dragging.handle,
  );
  const hints = new Map<string, Map<string, boolean>>();
  if (!from) return hints;
  for (const node of graph.nodes) {
    const marks = new Map<string, boolean>();
    if (dragging.side === "source") {
      for (const input of node.inputs)
        marks.set(`in:${input.name}`, node.id !== dragging.node && accepts(from, input, types));
    } else {
      for (const output of node.outputs)
        marks.set(`out:${output.name}`, node.id !== dragging.node && accepts(output, from, types));
    }
    hints.set(node.id, marks);
  }
  return hints;
}

function problemPorts(outcome: EditOutcome | null): ReadonlyMap<string, ReadonlySet<string>> {
  const ports = new Map<string, Set<string>>();
  const connection = outcome?.error?.connection;
  if (!connection) return ports;
  const add = (node: string, handle: string): void => {
    ports.set(node, (ports.get(node) ?? new Set()).add(handle));
  };
  if (connection.source.port) add(connection.source.node, `out:${connection.source.port}`);
  if (connection.target.port) add(connection.target.node, `in:${connection.target.port}`);
  return ports;
}

function isTyping(): boolean {
  const active = document.activeElement;
  return active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement;
}

function Editor(): ReactElement {
  const [graph, setGraph] = useState<ConfigGraph | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [types, setTypes] = useState<readonly NodeType[]>([]);
  const [payloadTypes, setPayloadTypes] = useState<ReadonlyMap<string, PayloadType>>(new Map());
  const [dragging, setDragging] = useState<Dragging | null>(null);
  const [edits, setEdits] = useState<readonly Edit[]>([]);
  const [previews, setPreviews] = useState<ReadonlyMap<string, ConfigNode>>(new Map());
  const [outcome, setOutcome] = useState<EditOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [metrics, setMetrics] = useState<ReadonlyMap<string, NodeMetrics>>(new Map());
  const [connected, setConnected] = useState(false);
  const [reloadError, setReloadError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>({});
  const [dialog, setDialog] = useState<{ from: { node: string; port: string } | null } | null>(null);
  const [positions, setPositions] = useState<Positions>(new Map());
  const [saved, setSaved] = useState<readonly string[]>([]);
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
        setPositions(p);
      },
      () => undefined,
    );
    return () => {
      current = false;
    };
  }, [shape]);

  // Fit the view to each new layout, once it is drawn and measured
  useEffect(() => {
    if (positions.size === 0) return undefined;
    const timer = window.setTimeout(() => void flow.fitView({ padding: 0.12, duration: 200 }), 60);
    return () => window.clearTimeout(timer);
  }, [positions, flow]);

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
    setBusy(true);
    try {
      setOutcome(await previewEdits(graph.version, edits));
      setStale(false);
    } finally {
      setBusy(false);
    }
  }, [graph, edits]);

  const save = useCallback(async (): Promise<void> => {
    if (!graph) return;
    setBusy(true);
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
      setBusy(false);
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

  const onConnectEnd = useCallback((_: unknown, state: FinalConnectionState): void => {
    setDragging(null);
    if (state.isValid || !state.fromNode || !state.fromHandle?.id || state.fromHandle.type !== "source") return;
    setDialog({ from: { node: state.fromNode.id, port: state.fromHandle.id.replace(/^out:/, "") } });
  }, []);

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

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (isTyping() || dialog) return;
      if (event.key === "Delete" || event.key === "Backspace") removeSelection();
      else if ((event.metaKey || event.ctrlKey) && event.key === "z") setEdits((current) => current.slice(0, -1));
      else if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        setDialog({ from: null });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [removeSelection, dialog]);

  const problems = useMemo(() => problemPorts(outcome), [outcome]);
  const hints = useMemo(
    () => (staged && dragging ? connectionHints(staged, dragging, payloadTypes) : null),
    [staged, dragging, payloadTypes],
  );

  const isValidConnection = useCallback(
    (connection: Edge | Connection): boolean => {
      if (!staged || !connection.sourceHandle || !connection.targetHandle) return true;
      const output = portOf(
        staged.nodes.find((n) => n.id === connection.source),
        connection.sourceHandle,
      );
      const input = portOf(
        staged.nodes.find((n) => n.id === connection.target),
        connection.targetHandle,
      );
      return output === undefined || input === undefined || accepts(output, input, payloadTypes);
    },
    [staged, payloadTypes],
  );

  const flowNodes: Node[] = useMemo(
    () =>
      (staged?.nodes ?? []).map((node) => ({
        id: node.id,
        type: "card",
        position: positions.get(node.id) ?? { x: 0, y: 0 },
        selected: selection.node === node.id,
        draggable: false,
        connectable: graph?.editable === true && node.status !== "removed",
        data: {
          node,
          metrics: metrics.get(node.renamedFrom ?? node.id),
          problemPorts: problems.get(node.id) ?? new Set(),
          hints: hints?.get(node.id) ?? null,
        } satisfies NodeCardData,
      })),
    [staged, positions, selection, metrics, problems, graph, hints],
  );

  const flowEdges: Edge[] = useMemo(() => {
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
          className: `edge-${e.status}${failing ? " edge-problem" : ""}`,
          label: e.repeat ? `×${e.repeat}` : e.repeatUntil ? `→${e.repeatUntil}` : undefined,
          markerEnd: { type: MarkerType.ArrowClosed },
        };
      });
  }, [staged, selection, outcome]);

  const selectedNode = staged?.nodes.find((n) => n.id === selection.node) ?? null;
  const selectedEdge = staged?.edges.find((e) => e.key === selection.edge) ?? null;
  const editable = graph?.editable === true;

  const onDoubleClick = (event: MouseEvent): void => {
    if (editable && (event.target as HTMLElement).classList.contains("react-flow__pane")) setDialog({ from: null });
  };

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">rasl</span>
        <span className="muted mono small">{graph?.path}</span>
        <span className="spacer" />
        {editable ? (
          <button className="button" onClick={() => setDialog({ from: null })}>
            Add node (⌘K)
          </button>
        ) : null}
        <span className={`conn ${connected ? "on" : "off"}`}>{connected ? "live" : "offline"}</span>
      </header>
      {loadError ? <div className="banner error">{loadError}</div> : null}
      {reloadError ? <div className="banner error">The running graph did not reload: {reloadError}</div> : null}
      {graph?.error && edits.length === 0 ? (
        <div className="banner warning">The config does not build: {graph.error.message}</div>
      ) : null}
      <main className="layout">
        <section className="canvas" onDoubleClick={onDoubleClick}>
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={NODE_TYPES}
            onConnect={onConnect}
            onConnectEnd={onConnectEnd}
            onConnectStart={(_, start) => {
              if (start.nodeId && start.handleId && start.handleType) {
                setDragging({ node: start.nodeId, handle: start.handleId, side: start.handleType });
              }
            }}
            isValidConnection={isValidConnection}
            onNodeClick={(_, node) => setSelection({ node: node.id })}
            onEdgeClick={(_, edge) => setSelection({ edge: edge.id })}
            onPaneClick={() => setSelection({})}
            nodesConnectable={editable}
            deleteKeyCode={null}
            zoomOnDoubleClick={false}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls showInteractive={false} />
          </ReactFlow>
        </section>
        <aside className="side">
          <Inspector
            node={selectedNode}
            edge={selectedEdge}
            metrics={selectedNode ? metrics.get(selectedNode.renamedFrom ?? selectedNode.id) : undefined}
            editable={editable}
            onRename={(id, newId) => push({ renameNode: { id, newId } })}
            onRemove={(id) => push({ removeNode: { id } })}
            onDisconnect={(edge) => push({ disconnect: { source: edge.source, target: edge.target, port: edge.port } })}
            schema={
              types.find((t) => t.name === selectedNode?.type || t.aliases.includes(selectedNode?.type ?? ""))
                ?.schema ?? null
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
        </aside>
      </main>
      {dialog && staged ? (
        <AddNodeDialog
          types={types}
          takenIds={new Set(staged.nodes.map((n) => n.id))}
          from={dialog.from}
          onAdd={addNode}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </div>
  );
}

export function App(): ReactElement {
  return (
    <ReactFlowProvider>
      <Editor />
    </ReactFlowProvider>
  );
}
