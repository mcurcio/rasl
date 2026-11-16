// The graph the editor shows: the config as written with the queued edits laid over it.
// Pure functions only; the components render what these return.
import type { ConfigEdge, ConfigGraph, ConfigNode, Edit, Port, Setting } from "./api";

/** How a node or connection differs from the saved files. */
export const Statuses = { Saved: "saved", Added: "added", Removed: "removed", Renamed: "renamed" } as const;
export type Status = (typeof Statuses)[keyof typeof Statuses];

export type ViewNode = {
  readonly id: string;
  readonly type: string;
  readonly status: Status;
  readonly renamedFrom: string | null;
  readonly inputs: readonly Port[];
  readonly outputs: readonly Port[];
  readonly settings: readonly Setting[];
  readonly locked: string | null;
  readonly error: string | null;
  readonly place: ConfigNode["place"] | null;
};

export type ViewEdge = {
  /** Stable while staged: the line's target, source and port as written. */
  readonly key: string;
  readonly target: string;
  readonly source: string;
  readonly port: string | null;
  readonly sourceNode: string | null;
  readonly sourcePort: string | null;
  readonly targetPort: string | null;
  readonly repeat: number | null;
  readonly repeatUntil: number | null;
  readonly status: Status;
  readonly locked: string | null;
  readonly place: ConfigEdge["place"] | null;
};

export type StagedGraph = { readonly nodes: readonly ViewNode[]; readonly edges: readonly ViewEdge[] };

export type SourceRef = {
  readonly node: string;
  readonly port: string | null;
  readonly sliceStart: number | null;
  readonly sliceEnd: number | null;
};

const REF = /^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d*)~(\d*)\])?(?:\.([A-Za-z_][A-Za-z0-9_]*))?(?:\[(\d*)~(\d*)\])?$/;

function bound(text: string | undefined): number | null {
  return text === undefined || text === "" ? null : Number(text);
}

/** A port reference in config notation (`hue.out[0~3]`), or undefined when it is not one. */
export function parseRef(text: string): SourceRef | undefined {
  const match = REF.exec(text);
  if (!match) return undefined;
  const [, node = "", s1, e1, port, s2, e2] = match;
  const sliced = s2 !== undefined || e2 !== undefined;
  return {
    node,
    port: port ?? null,
    sliceStart: bound(sliced ? s2 : s1),
    sliceEnd: bound(sliced ? e2 : e1),
  };
}

export function edgeKey(target: string, source: string, port: string | null): string {
  return `${target}|${source}|${port ?? ""}`;
}

function defaultPort(ports: readonly Port[]): string | null {
  return ports.find((p) => p.default)?.name ?? null;
}

function renameRef(text: string, from: string, to: string): string {
  return text.replace(new RegExp(`^${from}(?=$|[.[])`), to);
}

/** The saved graph with ``edits`` laid over it. ``previews`` gives added nodes their ports. */
export function stage(
  base: ConfigGraph,
  edits: readonly Edit[],
  previews: ReadonlyMap<string, ConfigNode>,
): StagedGraph {
  let nodes: ViewNode[] = base.nodes.map((n) => ({
    id: n.id,
    type: n.type,
    status: Statuses.Saved,
    renamedFrom: null,
    inputs: n.inputs,
    outputs: n.outputs,
    settings: n.settings,
    locked: n.locked,
    error: n.error,
    place: n.place,
  }));
  let edges: ViewEdge[] = base.edges.map((e) => ({
    key: edgeKey(e.target, e.source, e.port),
    target: e.target,
    source: e.source,
    port: e.port,
    sourceNode: e.sourceNode,
    sourcePort: e.sourcePort,
    targetPort: e.targetPort,
    repeat: e.repeat,
    repeatUntil: e.repeatUntil,
    status: Statuses.Saved,
    locked: e.locked,
    place: e.place,
  }));

  for (const edit of edits) {
    if ("addNode" in edit) {
      const { type, id, settings } = edit.addNode;
      const preview = previews.get(id);
      nodes.push({
        id,
        type,
        status: Statuses.Added,
        renamedFrom: null,
        inputs: preview?.inputs ?? [],
        outputs: preview?.outputs ?? [],
        settings,
        locked: null,
        error: preview?.error ?? null,
        place: null,
      });
    } else if ("removeNode" in edit) {
      const { id } = edit.removeNode;
      nodes = nodes.map((n) => (n.id === id ? { ...n, status: Statuses.Removed } : n));
      edges = edges.map((e) => (e.target === id || e.sourceNode === id ? { ...e, status: Statuses.Removed } : e));
    } else if ("renameNode" in edit) {
      const { id, newId } = edit.renameNode;
      nodes = nodes.map((n) =>
        n.id === id
          ? {
              ...n,
              id: newId,
              renamedFrom: n.renamedFrom ?? id,
              status: n.status === Statuses.Saved ? Statuses.Renamed : n.status,
            }
          : n,
      );
      edges = edges.map((e) => {
        if (e.target !== id && e.sourceNode !== id) return e;
        const target = e.target === id ? newId : e.target;
        const source = e.sourceNode === id ? renameRef(e.source, id, newId) : e.source;
        return {
          ...e,
          target,
          source,
          sourceNode: e.sourceNode === id ? newId : e.sourceNode,
          key: edgeKey(target, source, e.port),
        };
      });
    } else if ("connect" in edit) {
      const { source, target, port, repeat, repeatUntil } = edit.connect;
      const ref = parseRef(source);
      const from = nodes.find((n) => n.id === ref?.node);
      const to = nodes.find((n) => n.id === target);
      edges.push({
        key: edgeKey(target, source, port),
        target,
        source,
        port,
        sourceNode: ref?.node ?? null,
        sourcePort: ref?.port ?? (from ? defaultPort(from.outputs) : null),
        targetPort: port !== null ? (parseRef(port)?.node ?? null) : to ? defaultPort(to.inputs) : null,
        repeat,
        repeatUntil,
        status: Statuses.Added,
        locked: null,
        place: null,
      });
    } else {
      const { source, target, port } = edit.disconnect;
      const key = edgeKey(target, source, port);
      edges = edges.map((e) => (e.key === key ? { ...e, status: Statuses.Removed } : e));
    }
  }
  return { nodes, edges };
}

/**
 * ``edits`` with ``edit`` queued. Undoing a queued edit cancels it instead of queueing its
 * opposite: removing a node added in this batch drops it and its connections, and
 * disconnecting a connection added in this batch drops the connect.
 */
export function queue(edits: readonly Edit[], edit: Edit): readonly Edit[] {
  if ("removeNode" in edit) {
    const { id } = edit.removeNode;
    const added = edits.some((e) => "addNode" in e && e.addNode.id === id);
    if (added) {
      return edits.filter(
        (e) =>
          !("addNode" in e && e.addNode.id === id) &&
          !("connect" in e && (e.connect.target === id || parseRef(e.connect.source)?.node === id)),
      );
    }
  }
  if ("disconnect" in edit) {
    const { source, target, port } = edit.disconnect;
    const index = edits.findIndex(
      (e) => "connect" in e && e.connect.source === source && e.connect.target === target && e.connect.port === port,
    );
    if (index >= 0) return edits.filter((_, i) => i !== index);
  }
  return [...edits, edit];
}

/** A connection's text from handle names: the port is left out where it is the default. */
export function connectEdit(from: ViewNode, sourcePort: string, to: ViewNode, targetPort: string): Edit {
  const source = defaultPort(from.outputs) === sourcePort ? from.id : `${from.id}.${sourcePort}`;
  const port = defaultPort(to.inputs) === targetPort ? null : targetPort;
  return { connect: { source, target: to.id, port, repeat: null, repeatUntil: null } };
}

/** A free id for a new node of ``type``: the type in snake case, numbered. */
export function nextId(type: string, taken: ReadonlySet<string>): string {
  const stem = type
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^A-Za-z0-9_]/g, "_")
    .toLowerCase();
  for (let n = 1; ; n += 1) {
    const id = `${stem}_${n}`;
    if (!taken.has(id)) return id;
  }
}

/** A one-line description of an edit, for the queue. */
export function describe(edit: Edit): string {
  if ("addNode" in edit) return `add ${edit.addNode.type} ${edit.addNode.id}`;
  if ("removeNode" in edit) return `remove ${edit.removeNode.id}`;
  if ("renameNode" in edit) return `rename ${edit.renameNode.id} → ${edit.renameNode.newId}`;
  if ("connect" in edit) {
    const c = edit.connect;
    return `connect ${c.source} → ${c.target}${c.port ? `.${c.port}` : ""}${c.repeat ? ` ×${c.repeat}` : ""}`;
  }
  const d = edit.disconnect;
  return `disconnect ${d.source} → ${d.target}${d.port ? `.${d.port}` : ""}`;
}
