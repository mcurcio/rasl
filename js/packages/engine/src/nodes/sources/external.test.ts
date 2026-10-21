import { describe, expect, it } from "vitest";

import { createTickContext } from "../../runtime/tick.js";
import { MatrixPayload } from "../../runtime/payloads/index.js";
import { ExternalSourceNode } from "./external.js";

function readValues(node: ExternalSourceNode): number[] {
  const frame = node.outputs.get("out")?._consume();
  expect(frame).toBeTruthy();
  return Array.from((frame!.payload as MatrixPayload).flatten());
}

describe("ExternalSourceNode", () => {
  it("emits zero initial values by default", async () => {
    const node = new ExternalSourceNode({ id: "external", size: 4 });

    await node.pull(createTickContext({ tick: 1, t: 0, dt: 0, wallTime: 0 }));

    expect(readValues(node)).toEqual([0, 0, 0, 0]);
  });

  it("accepts normalized updates and holds the last value", async () => {
    const node = new ExternalSourceNode({ id: "external", size: 3 });

    node.setExternalValues(new Float32Array([0, 0.5, 1]));
    await node.pull(createTickContext({ tick: 1, t: 0, dt: 0, wallTime: 0 }));
    expect(readValues(node)).toEqual([0, 0.5, 1]);

    await node.pull(createTickContext({ tick: 2, t: 1, dt: 1, wallTime: 1 }));
    expect(readValues(node)).toEqual([0, 0.5, 1]);
  });

  it("rejects invalid updates without changing held state", async () => {
    const node = new ExternalSourceNode({ id: "external", size: 2, initial: 0.25 });

    expect(() => node.setExternalValues(new Float32Array([0.5]))).toThrow(/expected 2 values/i);
    expect(() => node.setExternalValues(new Float32Array([0.5, 1.5]))).toThrow(/\[0, 1\]/);

    await node.pull(createTickContext({ tick: 1, t: 0, dt: 0, wallTime: 0 }));
    expect(readValues(node)).toEqual([0.25, 0.25]);
  });

  it("requires size to be divisible by channels", () => {
    expect(() => new ExternalSourceNode({ id: "external", size: 5, channels: 2 })).toThrow(/divisible/);
  });
});
