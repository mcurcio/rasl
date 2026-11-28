// The graph the editor shows: the config as written with the queued edits laid over it.
// Pure functions only; the components render what these return.
import type { ConfigEdge, ConfigGraph, ConfigNode, Edit, PayloadType, Port, Setting, SettingLine } from "./api";

/** How a node or connection differs from the saved files. */
export const Statuses = {
  Saved: "saved",
  Added: "added",
  Removed: "removed",
  Renamed: "renamed",
  Changed: "changed",
} as const;
export type Status = (typeof Statuses)[keyof typeof Statuses];

export type ViewNode = {
  readonly id: string;
  readonly type: string;
  readonly status: Status;
  readonly renamedFrom: string | null;
  readonly inputs: readonly Port[];
  readonly outputs: readonly Port[];
  readonly values: string;
  readonly use: string | null;
  readonly settings: readonly ViewSetting[];
  readonly locked: string | null;
  readonly error: string | null;
  readonly place: ConfigNode["place"] | null;
};

/** A node's setting line, with any queued change to it. */
export type ViewSetting = SettingLine & {
  /** Set when a queued edit changes it: the values queued, and where they are written. */
  readonly queued: { readonly values: string; readonly scope: "line" | "definition" } | null;
  readonly removed: boolean;
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
    values: n.values,
    use: n.use,
    settings: n.settings.map((setting) => ({ ...setting, queued: null, removed: false })),
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
        values: edit.addNode.values,
        use: null,
        settings: settings.map((setting, i) => ({
          key: setting.key,
          index: settings.slice(0, i).filter((s) => s.key === setting.key).length,
          values: setting.values,
          written: setting.values,
          locked: null,
          definition: null,
          hasBlock: false,
          queued: null,
          removed: false,
        })),
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
    } else if ("disconnect" in edit) {
      const { source, target, port } = edit.disconnect;
      const key = edgeKey(target, source, port);
      edges = edges.map((e) => (e.key === key ? { ...e, status: Statuses.Removed } : e));
    } else if ("setSetting" in edit) {
      const { node, key, values, index, scope } = edit.setSetting;
      nodes = nodes.map((n) => {
        if (n.id !== node) return n;
        const exists = n.settings.some((s) => s.key === key && s.index === index);
        const settings: ViewSetting[] = exists
          ? n.settings.map((s) => (s.key === key && s.index === index ? { ...s, queued: { values, scope } } : s))
          : [
              ...n.settings,
              {
                key,
                index,
                values,
                written: values,
                locked: null,
                definition: null,
                hasBlock: false,
                queued: { values, scope },
                removed: false,
              },
            ];
        return { ...n, settings, status: changed(n.status) };
      });
    } else if ("removeSetting" in edit) {
      const { node, key, index } = edit.removeSetting;
      nodes = nodes.map((n) =>
        n.id === node
          ? {
              ...n,
              settings: n.settings.map((s) => (s.key === key && s.index === index ? { ...s, removed: true } : s)),
              status: changed(n.status),
            }
          : n,
      );
    } else if ("setNodeValues" in edit) {
      const { node, values } = edit.setNodeValues;
      nodes = nodes.map((n) => (n.id === node ? { ...n, values, status: changed(n.status) } : n));
    } else {
      const { id } = edit.detach;
      nodes = nodes.map((n) => (n.id === id ? { ...n, use: null, locked: null, status: changed(n.status) } : n));
    }
  }
  return { nodes, edges };
}

function changed(status: Status): Status {
  return status === Statuses.Saved ? Statuses.Changed : status;
}

/**
 * Whether ``input`` takes what ``output`` emits: one of its types takes the output's type,
 * as it is or retyped, with the same width when both are known. A port of a type the
 * server did not list is not judged here (the server checks every edit).
 */
export function accepts(output: Port, input: Port, types: ReadonlyMap<string, PayloadType>): boolean {
  const emitted = output.types[0];
  if (emitted === undefined || input.types.length === 0) return true;
  return input.types.some((name) => {
    const type = types.get(name);
    if (type === undefined) return true;
    if (!type.takes.includes(emitted)) return false;
    return type.components === null || output.components === null || type.components === output.components;
  });
}

/** Where a node named ``name`` now came from: its name in the saved files, or that it was added in ``edits``. */
function originOf(edits: readonly Edit[], name: string): { readonly name: string; readonly added: boolean } {
  let current = name;
  for (let i = edits.length - 1; i >= 0; i -= 1) {
    const e = edits[i]!;
    if ("renameNode" in e && e.renameNode.newId === current) current = e.renameNode.id;
    else if ("addNode" in e && e.addNode.id === current) return { name: current, added: true };
  }
  return { name: current, added: false };
}

/** ``edit`` with every reference to the node ``from`` made to ``to``. */
function retarget(edit: Edit, from: string, to: string): Edit {
  const node = (id: string): string => (id === from ? to : id);
  if ("removeNode" in edit) return { removeNode: { id: node(edit.removeNode.id) } };
  if ("renameNode" in edit) return { renameNode: { ...edit.renameNode, id: node(edit.renameNode.id) } };
  if ("connect" in edit)
    return {
      connect: { ...edit.connect, source: renameRef(edit.connect.source, from, to), target: node(edit.connect.target) },
    };
  if ("disconnect" in edit)
    return {
      disconnect: {
        ...edit.disconnect,
        source: renameRef(edit.disconnect.source, from, to),
        target: node(edit.disconnect.target),
      },
    };
  if ("setSetting" in edit) return { setSetting: { ...edit.setSetting, node: node(edit.setSetting.node) } };
  if ("removeSetting" in edit) return { removeSetting: { ...edit.removeSetting, node: node(edit.removeSetting.node) } };
  if ("setNodeValues" in edit) return { setNodeValues: { ...edit.setNodeValues, node: node(edit.setNodeValues.node) } };
  if ("detach" in edit) return { detach: { id: node(edit.detach.id) } };
  return edit;
}

/**
 * Renaming a node back to the name the saved files give it: the queued renames that led from that name are dropped,
 * and the edits queued between them name the node by it again. Undefined when ``edit`` is not such a rename.
 */
function renameBack(
  edits: readonly Edit[],
  edit: { readonly id: string; readonly newId: string },
): readonly Edit[] | undefined {
  const chain = new Set<number>();
  let name = edit.id;
  for (let i = edits.length - 1; i >= 0; i -= 1) {
    const e = edits[i]!;
    if ("renameNode" in e && e.renameNode.newId === name) {
      chain.add(i);
      name = e.renameNode.id;
    } else if ("addNode" in e && e.addNode.id === name) return undefined;
  }
  if (chain.size === 0 || name !== edit.newId) return undefined;
  const origin = name;
  let current = origin;
  const kept: Edit[] = [];
  edits.forEach((e, i) => {
    if (chain.has(i) && "renameNode" in e) current = e.renameNode.newId;
    else kept.push(current === origin ? e : retarget(e, current, origin));
  });
  return kept;
}

/** ``settings`` with the ``index``-th line of ``key`` given ``values`` (appended when there is none), or removed. */
function foldSetting(
  settings: readonly Setting[],
  key: string,
  index: number,
  values: string | null,
): readonly Setting[] {
  let seen = -1;
  let found = false;
  const next: Setting[] = [];
  for (const s of settings) {
    if (s.key === key) seen += 1;
    if (s.key === key && seen === index) {
      found = true;
      if (values !== null) next.push({ key, values });
    } else next.push(s);
  }
  if (!found && values !== null) next.push({ key, values });
  return next;
}

/**
 * ``edits`` with ``edit`` queued, keeping only the net change (patchbay's ChangeList rule): queuing the reverse of a
 * queued change drops it rather than adding a second.
 *
 * - Removing a node added in this batch drops the add and every queued change that names it.
 * - A change to a node added in this batch folds into the add, which stays one added change with the new settings or
 *   values.
 * - Disconnecting a connection queued in this batch drops the connect; connecting again a saved connection whose
 *   disconnect is queued (with the same repeat) drops the disconnect.
 * - Renaming a node back to the name the saved files give it drops the renames that led from it.
 * - A later value for a setting line, or for a node's values, replaces the queued one; a value the saved files
 *   already hold (``base``) drops it.
 */
export function queue(edits: readonly Edit[], edit: Edit, base?: ConfigGraph): readonly Edit[] {
  const addOf = (id: string): number => edits.findIndex((e) => "addNode" in e && e.addNode.id === id);
  const savedNode = (name: string): ConfigNode | undefined => {
    const origin = originOf(edits, name);
    return origin.added ? undefined : base?.nodes.find((n) => n.id === origin.name);
  };

  if ("removeNode" in edit) {
    const { id } = edit.removeNode;
    if (addOf(id) >= 0) {
      return edits.filter((e) => {
        if ("addNode" in e) return e.addNode.id !== id;
        if ("connect" in e) return e.connect.target !== id && parseRef(e.connect.source)?.node !== id;
        if ("disconnect" in e) return e.disconnect.target !== id && parseRef(e.disconnect.source)?.node !== id;
        if ("setSetting" in e) return e.setSetting.node !== id;
        if ("removeSetting" in e) return e.removeSetting.node !== id;
        if ("setNodeValues" in e) return e.setNodeValues.node !== id;
        if ("renameNode" in e) return e.renameNode.id !== id && e.renameNode.newId !== id;
        if ("detach" in e) return e.detach.id !== id;
        return e.removeNode.id !== id;
      });
    }
  }
  if ("renameNode" in edit) {
    const back = renameBack(edits, edit.renameNode);
    if (back) return back;
  }
  if ("setSetting" in edit || "removeSetting" in edit || "setNodeValues" in edit) {
    const id =
      "setSetting" in edit
        ? edit.setSetting.node
        : "removeSetting" in edit
          ? edit.removeSetting.node
          : edit.setNodeValues.node;
    const at = addOf(id);
    const added = edits[at];
    if (added && "addNode" in added) {
      const add = added.addNode;
      const folded: Edit = {
        addNode:
          "setSetting" in edit
            ? {
                ...add,
                settings: foldSetting(add.settings, edit.setSetting.key, edit.setSetting.index, edit.setSetting.values),
              }
            : "removeSetting" in edit
              ? { ...add, settings: foldSetting(add.settings, edit.removeSetting.key, edit.removeSetting.index, null) }
              : { ...add, values: edit.setNodeValues.values },
      };
      return edits.map((e, i) => (i === at ? folded : e));
    }
  }
  if ("setSetting" in edit) {
    const { node, key, index, values } = edit.setSetting;
    const kept = edits.filter(
      (e) =>
        !("setSetting" in e && e.setSetting.node === node && e.setSetting.key === key && e.setSetting.index === index),
    );
    const saved = savedNode(node)?.settings.find((s) => s.key === key && s.index === index);
    return saved !== undefined && saved.values === values ? kept : [...kept, edit];
  }
  if ("setNodeValues" in edit) {
    const { node, values } = edit.setNodeValues;
    const kept = edits.filter((e) => !("setNodeValues" in e && e.setNodeValues.node === node));
    return savedNode(node)?.values === values ? kept : [...kept, edit];
  }
  if ("disconnect" in edit) {
    const { source, target, port } = edit.disconnect;
    const index = edits.findIndex(
      (e) => "connect" in e && e.connect.source === source && e.connect.target === target && e.connect.port === port,
    );
    if (index >= 0) return edits.filter((_, i) => i !== index);
  }
  if ("connect" in edit) {
    const { source, target, port, repeat, repeatUntil } = edit.connect;
    const index = edits.findIndex(
      (e) =>
        "disconnect" in e &&
        e.disconnect.source === source &&
        e.disconnect.target === target &&
        e.disconnect.port === port,
    );
    const saved = base?.edges.find((e) => e.source === source && e.target === target && e.port === port);
    if (index >= 0 && saved !== undefined && saved.repeat === repeat && saved.repeatUntil === repeatUntil)
      return edits.filter((_, i) => i !== index);
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

/** A queued edit as the queue lists it: what it does (patchbay's change kinds), what it names, and what changes. */
export type ChangeWords = {
  readonly change: "added" | "removed" | "renamed" | "changed";
  readonly label: string;
  readonly detail: string;
};

function connectionLabel(c: {
  readonly source: string;
  readonly target: string;
  readonly port: string | null;
}): string {
  return `${c.source} → ${c.target}${c.port ? `.${c.port}` : ""}`;
}

/** An edit's words for the queue's list. */
export function changeOf(edit: Edit): ChangeWords {
  if ("addNode" in edit) {
    const settings = edit.addNode.settings.map((s) => `${s.key} ${s.values}`);
    const values = edit.addNode.values ? [edit.addNode.values] : [];
    return {
      change: "added",
      label: edit.addNode.id,
      detail: [`node ${edit.addNode.type}`, ...values, ...settings].join(" · "),
    };
  }
  if ("removeNode" in edit) return { change: "removed", label: edit.removeNode.id, detail: "node" };
  if ("renameNode" in edit)
    return { change: "renamed", label: `${edit.renameNode.id} → ${edit.renameNode.newId}`, detail: "node" };
  if ("connect" in edit) {
    const c = edit.connect;
    const repeat = c.repeat ? ` ×${c.repeat}` : c.repeatUntil ? ` →${c.repeatUntil}` : "";
    return { change: "added", label: connectionLabel(c), detail: `connection${repeat}` };
  }
  if ("disconnect" in edit) return { change: "removed", label: connectionLabel(edit.disconnect), detail: "connection" };
  if ("setSetting" in edit) {
    const s = edit.setSetting;
    return {
      change: "changed",
      label: `${s.node}.${s.key}${s.index > 0 ? `[${s.index}]` : ""}`,
      detail: `${s.values}${s.scope === "definition" ? " (at its definition)" : ""}`,
    };
  }
  if ("removeSetting" in edit) {
    const s = edit.removeSetting;
    return { change: "removed", label: `${s.node}.${s.key}${s.index > 0 ? `[${s.index}]` : ""}`, detail: "setting" };
  }
  if ("setNodeValues" in edit)
    return {
      change: "changed",
      label: `${edit.setNodeValues.node} values`,
      detail: edit.setNodeValues.values || "(none)",
    };
  return { change: "changed", label: edit.detach.id, detail: "detached from its @use" };
}
