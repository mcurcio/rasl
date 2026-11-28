import { describe as group, expect, it } from "vitest";

import type { ConfigGraph, Edit, Port } from "./api";
import { accepts, changeOf, connectEdit, nextId, parseRef, queue, stage, Statuses } from "./model";

const port = (name: string, isDefault = true): Port => ({
  name,
  types: ["matrix"],
  minCount: null,
  maxCount: null,
  components: null,
  default: isDefault,
});

const BASE: ConfigGraph = {
  path: "rasl.conf",
  version: "v1",
  editable: true,
  error: null,
  nodes: [
    {
      id: "wave",
      type: "Waveform",
      place: { path: "rasl.conf", line: 2 },
      locked: null,
      values: "",
      use: null,
      settings: [],
      inputs: [],
      outputs: [port("out")],
      error: null,
    },
    {
      id: "sink",
      type: "ConsoleSink",
      place: { path: "rasl.conf", line: 3 },
      locked: null,
      values: "",
      use: null,
      settings: [],
      inputs: [port("dmx")],
      outputs: [],
      error: null,
    },
  ],
  edges: [
    {
      target: "sink",
      source: "wave",
      port: null,
      sourceNode: "wave",
      sourcePort: "out",
      targetPort: "dmx",
      repeat: null,
      repeatUntil: null,
      place: { path: "rasl.conf", line: 4 },
      locked: null,
    },
  ],
};

group("parseRef", () => {
  it("reads node, port and either slice position", () => {
    expect(parseRef("hue.out[0~3]")).toEqual({ node: "hue", port: "out", sliceStart: 0, sliceEnd: 3 });
    expect(parseRef("hue[2~]")).toEqual({ node: "hue", port: null, sliceStart: 2, sliceEnd: null });
    expect(parseRef("not a ref")).toBeUndefined();
  });
});

group("stage", () => {
  it("shows an added node with its previewed ports and its connection", () => {
    const edits: Edit[] = [
      { addNode: { type: "ConsoleSink", id: "debug", values: "", settings: [] } },
      { connect: { source: "wave", target: "debug", port: null, repeat: null, repeatUntil: null } },
    ];
    const previews = new Map([["debug", { ...BASE.nodes[1]!, id: "debug" }]]);
    const staged = stage(BASE, edits, previews);
    expect(staged.nodes.find((n) => n.id === "debug")?.status).toBe(Statuses.Added);
    const edge = staged.edges.find((e) => e.target === "debug");
    expect(edge).toMatchObject({ status: Statuses.Added, sourcePort: "out", targetPort: "dmx" });
  });

  it("marks a removed node and its connections removed", () => {
    const staged = stage(BASE, [{ removeNode: { id: "wave" } }], new Map());
    expect(staged.nodes.find((n) => n.id === "wave")?.status).toBe(Statuses.Removed);
    expect(staged.edges[0]?.status).toBe(Statuses.Removed);
  });

  it("follows a rename into the connections that read the node", () => {
    const staged = stage(BASE, [{ renameNode: { id: "wave", newId: "hue" } }], new Map());
    expect(staged.nodes[0]).toMatchObject({ id: "hue", renamedFrom: "wave", status: Statuses.Renamed });
    expect(staged.edges[0]).toMatchObject({ source: "hue", sourceNode: "hue", key: "sink|hue|" });
  });
});

group("queue", () => {
  it("cancels a queued connect instead of disconnecting it", () => {
    const connect: Edit = { connect: { source: "wave", target: "sink", port: "dmx", repeat: null, repeatUntil: null } };
    expect(queue([connect], { disconnect: { source: "wave", target: "sink", port: "dmx" } })).toEqual([]);
  });

  it("drops a queued node and its queued connections when it is removed", () => {
    const edits: Edit[] = [
      { addNode: { type: "ConsoleSink", id: "debug", values: "", settings: [] } },
      { connect: { source: "wave", target: "debug", port: null, repeat: null, repeatUntil: null } },
    ];
    expect(queue(edits, { removeNode: { id: "debug" } })).toEqual([]);
  });

  it("folds a change to a node added in the batch into the add", () => {
    const add: Edit = {
      addNode: { type: "ConsoleSink", id: "debug", values: "", settings: [{ key: "fps", values: "1" }] },
    };
    let edits = queue([add], { setSetting: { node: "debug", key: "fps", values: "4", index: 0, scope: "line" } }, BASE);
    edits = queue(edits, { setSetting: { node: "debug", key: "max_channels", values: "3", index: 0, scope: "line" } });
    edits = queue(edits, { setNodeValues: { node: "debug", values: "x" } });
    expect(edits).toEqual([
      {
        addNode: {
          type: "ConsoleSink",
          id: "debug",
          values: "x",
          settings: [
            { key: "fps", values: "4" },
            { key: "max_channels", values: "3" },
          ],
        },
      },
    ]);
    expect(queue(edits, { removeSetting: { node: "debug", key: "fps", index: 0 } })).toEqual([
      { addNode: { type: "ConsoleSink", id: "debug", values: "x", settings: [{ key: "max_channels", values: "3" }] } },
    ]);
  });

  it("drops a queued disconnect when the saved connection is made again", () => {
    const disconnect: Edit = { disconnect: { source: "wave", target: "sink", port: null } };
    const connect: Edit = { connect: { source: "wave", target: "sink", port: null, repeat: null, repeatUntil: null } };
    expect(queue([disconnect], connect, BASE)).toEqual([]);
    // With another repeat it is a change of its own
    expect(queue([disconnect], { connect: { ...connect.connect, repeat: 2 } }, BASE)).toHaveLength(2);
  });

  it("drops the renames when a node is renamed back, naming it by its saved name again", () => {
    const edits: Edit[] = [
      { renameNode: { id: "wave", newId: "hue" } },
      { setSetting: { node: "hue", key: "fps", values: "4", index: 0, scope: "line" } },
      { renameNode: { id: "hue", newId: "tone" } },
      { connect: { source: "tone.out", target: "sink", port: null, repeat: null, repeatUntil: null } },
    ];
    expect(queue(edits, { renameNode: { id: "tone", newId: "wave" } }, BASE)).toEqual([
      { setSetting: { node: "wave", key: "fps", values: "4", index: 0, scope: "line" } },
      { connect: { source: "wave.out", target: "sink", port: null, repeat: null, repeatUntil: null } },
    ]);
    // Renamed onward, the renames stay
    expect(queue(edits, { renameNode: { id: "tone", newId: "other" } }, BASE)).toHaveLength(5);
  });
});

group("connectEdit", () => {
  it("leaves default ports out of the text", () => {
    const [wave, sink] = stage(BASE, [], new Map()).nodes;
    expect(connectEdit(wave!, "out", sink!, "dmx")).toEqual({
      connect: { source: "wave", target: "sink", port: null, repeat: null, repeatUntil: null },
    });
  });
});

group("nextId", () => {
  it("numbers the snake-cased type past taken ids", () => {
    expect(nextId("ConsoleSink", new Set(["console_sink_1"]))).toBe("console_sink_2");
  });
});

group("settings", () => {
  it("stages a queued value on its line and marks the node changed", () => {
    const base: ConfigGraph = {
      ...BASE,
      nodes: [
        {
          ...BASE.nodes[0]!,
          settings: [
            { key: "fps", index: 0, values: "30", written: "$rate", locked: null, definition: null, hasBlock: false },
          ],
        },
        BASE.nodes[1]!,
      ],
    };
    const staged = stage(
      base,
      [{ setSetting: { node: "wave", key: "fps", values: "60", index: 0, scope: "definition" } }],
      new Map(),
    );
    const wave = staged.nodes[0]!;
    expect(wave.status).toBe(Statuses.Changed);
    expect(wave.settings[0]?.queued).toEqual({ values: "60", scope: "definition" });
  });

  it("keeps only the last queued value for a line", () => {
    const first: Edit = { setSetting: { node: "wave", key: "fps", values: "1", index: 0, scope: "line" } };
    const second: Edit = { setSetting: { node: "wave", key: "fps", values: "2", index: 0, scope: "line" } };
    expect(queue([first], second)).toEqual([second]);
  });

  it("drops a queued value set back to the saved one, for a line and for a node's values", () => {
    const base: ConfigGraph = {
      ...BASE,
      nodes: [
        {
          ...BASE.nodes[0]!,
          values: "a",
          settings: [
            { key: "fps", index: 0, values: "30", written: "30", locked: null, definition: null, hasBlock: false },
          ],
        },
        BASE.nodes[1]!,
      ],
    };
    const set: Edit = { setSetting: { node: "wave", key: "fps", values: "60", index: 0, scope: "line" } };
    expect(queue([set], { setSetting: { ...set.setSetting, values: "30" } }, base)).toEqual([]);
    const values: Edit = { setNodeValues: { node: "wave", values: "b" } };
    expect(queue([values], { setNodeValues: { node: "wave", values: "c" } }, base)).toEqual([
      { setNodeValues: { node: "wave", values: "c" } },
    ]);
    expect(queue([values], { setNodeValues: { node: "wave", values: "a" } }, base)).toEqual([]);
  });
});

group("changeOf", () => {
  it("words each edit by its change kind", () => {
    expect(
      changeOf({ addNode: { type: "ConsoleSink", id: "debug", values: "", settings: [{ key: "fps", values: "1" }] } }),
    ).toEqual({ change: "added", label: "debug", detail: "node ConsoleSink · fps 1" });
    expect(changeOf({ disconnect: { source: "wave", target: "sink", port: "dmx" } })).toEqual({
      change: "removed",
      label: "wave → sink.dmx",
      detail: "connection",
    });
    expect(changeOf({ renameNode: { id: "a", newId: "b" } }).change).toBe("renamed");
    expect(changeOf({ setSetting: { node: "wave", key: "fps", values: "4", index: 1, scope: "definition" } })).toEqual({
      change: "changed",
      label: "wave.fps[1]",
      detail: "4 (at its definition)",
    });
  });
});

group("accepts", () => {
  const types = new Map([
    ["matrix", { name: "matrix", components: null, takes: ["matrix", "bool", "color:hsbk"] }],
    ["bool", { name: "bool", components: null, takes: ["bool", "matrix"] }],
    ["color:hsbk", { name: "color:hsbk", components: 4, takes: ["color:hsbk", "matrix"] }],
  ]);
  const out = (type: string, components: number | null = null): Port => ({ ...port("out"), types: [type], components });
  const input = (type: string): Port => ({ ...port("in"), types: [type] });

  it("takes a more general type retyped, and a known width only when it matches", () => {
    expect(accepts(out("matrix"), input("bool"), types)).toBe(true);
    expect(accepts(out("matrix", 4), input("color:hsbk"), types)).toBe(true);
    expect(accepts(out("matrix", 1), input("color:hsbk"), types)).toBe(false);
  });

  it("refuses a type outside the chain", () => {
    expect(accepts(out("color:hsbk"), input("bool"), types)).toBe(false);
  });
});
