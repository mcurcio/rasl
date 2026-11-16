import { describe as group, expect, it } from "vitest";

import type { ConfigGraph, Edit, Port } from "./api";
import { connectEdit, nextId, parseRef, queue, stage, Statuses } from "./model";

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
