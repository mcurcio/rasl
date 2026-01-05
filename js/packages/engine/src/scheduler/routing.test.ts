/**
 * Tests for edge routing - slice and repeat functionality.
 */

import { describe, expect, it } from "vitest";

import { Edge } from "../graph/edge.js";
import { Frame } from "../runtime/frame.js";
import { MatrixPayload } from "../runtime/payloads/matrix.js";

import { applyEdgeRouting, slicePayload, validateNonOverlappingTargets } from "./routing.js";

describe("slicePayload", () => {
  it("should return same payload for full slice", () => {
    const payload = new MatrixPayload([1, 2, 3, 4, 5, 6], 3);
    const sliced = slicePayload(payload, { start: 0, end: 2 });

    // Full slice returns same instance
    expect(sliced).toBe(payload);
  });

  it("should extract first element", () => {
    const payload = new MatrixPayload([1, 2, 3, 4, 5, 6], 3);
    const sliced = slicePayload(payload, { start: 0, end: 1 });

    expect(sliced.count).toBe(1);
    expect(sliced.channels).toBe(3);
    expect(Array.from(sliced.data)).toEqual([1, 2, 3]);
  });

  it("should extract last element", () => {
    const payload = new MatrixPayload([1, 2, 3, 4, 5, 6], 3);
    const sliced = slicePayload(payload, { start: 1, end: 2 });

    expect(sliced.count).toBe(1);
    expect(sliced.channels).toBe(3);
    expect(Array.from(sliced.data)).toEqual([4, 5, 6]);
  });

  it("should handle null end (to the end)", () => {
    const payload = new MatrixPayload([1, 2, 3, 4, 5, 6, 7, 8, 9], 3);
    const sliced = slicePayload(payload, { start: 1, end: null });

    expect(sliced.count).toBe(2);
    expect(sliced.channels).toBe(3);
    expect(Array.from(sliced.data)).toEqual([4, 5, 6, 7, 8, 9]);
  });

  it("should throw on out-of-bounds start", () => {
    const payload = new MatrixPayload([1, 2, 3], 1);

    expect(() => slicePayload(payload, { start: -1, end: 2 })).toThrow("out of bounds");
    expect(() => slicePayload(payload, { start: 5, end: 6 })).toThrow("out of bounds");
  });

  it("should throw on out-of-bounds end", () => {
    const payload = new MatrixPayload([1, 2, 3], 1);

    expect(() => slicePayload(payload, { start: 0, end: 5 })).toThrow("out of bounds");
  });

  it("should throw on invalid range (end < start)", () => {
    const payload = new MatrixPayload([1, 2, 3], 1);

    expect(() => slicePayload(payload, { start: 2, end: 1 })).toThrow("out of bounds");
  });
});

describe("applyEdgeRouting", () => {
  function createFrame(data: number[], channels: number): Frame {
    return new Frame({
      topic: "test",
      timestamp: 0,
      payload: new MatrixPayload(data, channels),
    });
  }

  it("should return same frame when no routing needed", () => {
    const frame = createFrame([1, 2, 3], 1);
    const edge = new Edge("src", "out", "tgt", "in");

    const routed = applyEdgeRouting(frame, edge);

    expect(routed).toBe(frame);
  });

  it("should apply source slice", () => {
    const frame = createFrame([1, 2, 3, 4, 5, 6], 3);
    const edge = new Edge("src", "out", "tgt", "in", {
      sourceSlice: { start: 0, end: 1 },
    });

    const routed = applyEdgeRouting(frame, edge);

    expect(routed).not.toBe(frame);
    const payload = routed.payload as MatrixPayload;
    expect(payload.count).toBe(1);
    expect(Array.from(payload.data)).toEqual([1, 2, 3]);
  });

  it("should apply repeat", () => {
    const frame = createFrame([1, 2, 3], 3);
    const edge = new Edge("src", "out", "tgt", "in", {
      repeat: 3,
    });

    const routed = applyEdgeRouting(frame, edge);

    expect(routed).not.toBe(frame);
    const payload = routed.payload as MatrixPayload;
    expect(payload.count).toBe(3);
    expect(Array.from(payload.data)).toEqual([1, 2, 3, 1, 2, 3, 1, 2, 3]);
  });

  it("should apply source slice then repeat", () => {
    const frame = createFrame([1, 2, 3, 4, 5, 6], 3);
    const edge = new Edge("src", "out", "tgt", "in", {
      sourceSlice: { start: 0, end: 1 },
      repeat: 2,
    });

    const routed = applyEdgeRouting(frame, edge);

    const payload = routed.payload as MatrixPayload;
    expect(payload.count).toBe(2);
    expect(Array.from(payload.data)).toEqual([1, 2, 3, 1, 2, 3]);
  });

  it("should validate target slice length", () => {
    const frame = createFrame([1, 2, 3], 1);
    const edge = new Edge("src", "out", "tgt", "in", {
      targetSlice: { start: 0, end: 5 },
    });

    expect(() => applyEdgeRouting(frame, edge)).toThrow("does not match target slice length");
  });

  it("should pass when target slice matches payload count", () => {
    const frame = createFrame([1, 2, 3], 1);
    const edge = new Edge("src", "out", "tgt", "in", {
      targetSlice: { start: 0, end: 3 },
    });

    const routed = applyEdgeRouting(frame, edge);
    expect(routed).toBe(frame); // No transformation needed
  });

  it("should throw on slicing non-MatrixPayload", () => {
    const frame = new Frame({
      topic: "test",
      timestamp: 0,
      payload: { describe: () => ({ typeName: "Custom", domain: "custom", attrs: {} }) } as any,
    });
    const edge = new Edge("src", "out", "tgt", "in", {
      sourceSlice: { start: 0, end: 1 },
    });

    expect(() => applyEdgeRouting(frame, edge)).toThrow("requires MatrixPayload");
  });

  it("should preserve frame metadata", () => {
    const frame = new Frame({
      topic: "test",
      timestamp: 123,
      payload: new MatrixPayload([1, 2, 3], 1),
      metadata: { key: "value" },
    });
    const edge = new Edge("src", "out", "tgt", "in", {
      repeat: 2,
    });

    const routed = applyEdgeRouting(frame, edge);

    expect(routed.topic).toBe("test");
    expect(routed.timestamp).toBe(123);
    expect(routed.metadata).toEqual({ key: "value" });
  });
});

describe("validateNonOverlappingTargets", () => {
  it("should pass for non-overlapping slices", () => {
    const edges = [
      new Edge("src1", "out", "tgt", "in", { targetSlice: { start: 0, end: 5 } }),
      new Edge("src2", "out", "tgt", "in", { targetSlice: { start: 5, end: 10 } }),
    ];

    expect(() => validateNonOverlappingTargets(edges)).not.toThrow();
  });

  it("should pass for adjacent slices", () => {
    const edges = [
      new Edge("src1", "out", "tgt", "in", { targetSlice: { start: 0, end: 3 } }),
      new Edge("src2", "out", "tgt", "in", { targetSlice: { start: 3, end: 6 } }),
      new Edge("src3", "out", "tgt", "in", { targetSlice: { start: 6, end: 9 } }),
    ];

    expect(() => validateNonOverlappingTargets(edges)).not.toThrow();
  });

  it("should throw for overlapping slices", () => {
    const edges = [
      new Edge("src1", "out", "tgt", "in", { targetSlice: { start: 0, end: 5 } }),
      new Edge("src2", "out", "tgt", "in", { targetSlice: { start: 3, end: 8 } }),
    ];

    expect(() => validateNonOverlappingTargets(edges)).toThrow("Overlapping target slices");
  });

  it("should throw for contained slices", () => {
    const edges = [
      new Edge("src1", "out", "tgt", "in", { targetSlice: { start: 0, end: 10 } }),
      new Edge("src2", "out", "tgt", "in", { targetSlice: { start: 2, end: 5 } }),
    ];

    expect(() => validateNonOverlappingTargets(edges)).toThrow("Overlapping target slices");
  });

  it("should handle null end (open-ended slices)", () => {
    const edges = [
      new Edge("src1", "out", "tgt", "in", { targetSlice: { start: 0, end: 5 } }),
      new Edge("src2", "out", "tgt", "in", { targetSlice: { start: 5, end: null } }),
    ];

    expect(() => validateNonOverlappingTargets(edges)).not.toThrow();
  });

  it("should throw for overlapping open-ended slices", () => {
    const edges = [
      new Edge("src1", "out", "tgt", "in", { targetSlice: { start: 0, end: null } }),
      new Edge("src2", "out", "tgt", "in", { targetSlice: { start: 5, end: 10 } }),
    ];

    expect(() => validateNonOverlappingTargets(edges)).toThrow("Overlapping target slices");
  });

  it("should pass for edges without target slices", () => {
    const edges = [
      new Edge("src1", "out", "tgt", "in"),
      new Edge("src2", "out", "tgt", "in"),
    ];

    // No target slices means no overlap validation needed
    expect(() => validateNonOverlappingTargets(edges)).not.toThrow();
  });

  it("should pass for single edge", () => {
    const edges = [new Edge("src1", "out", "tgt", "in", { targetSlice: { start: 0, end: 5 } })];

    expect(() => validateNonOverlappingTargets(edges)).not.toThrow();
  });
});
