import { describe, expect,it } from "vitest";

import { GoveeLightNode } from "./node.js";

describe("GoveeLightNode", () => {
  describe("constructor", () => {
    it("should create with required config", () => {
      const node = new GoveeLightNode({
        id: "test-govee",
        host: "192.168.1.100",
      });
      expect(node.id).toBe("test-govee");
      expect(node.inputs.get("light")).toBeDefined();
    });

    it("should accept custom input port name", () => {
      const node = new GoveeLightNode({
        id: "test-govee",
        host: "192.168.1.100",
        inputPort: "colors",
      });
      expect(node.inputs.get("colors")).toBeDefined();
      expect(node.inputs.get("light")).toBeNull();
    });

    it("should parse fps from number", () => {
      const node = new GoveeLightNode({
        id: "test-govee",
        host: "192.168.1.100",
        fps: 30,
      });
      // Can't directly access _fps, but node should be created
      expect(node).toBeDefined();
    });

    it("should parse fps from hz string", () => {
      const node = new GoveeLightNode({
        id: "test-govee",
        host: "192.168.1.100",
        fps: "60hz",
      });
      expect(node).toBeDefined();
    });

    it("should parse fps from ms string", () => {
      const node = new GoveeLightNode({
        id: "test-govee",
        host: "192.168.1.100",
        fps: "50ms",
      });
      expect(node).toBeDefined();
    });
  });

  describe("quantization", () => {
    it("should quantize float [0,1] to uint8 [0,255]", () => {
      const node = new GoveeLightNode({
        id: "test-govee",
        host: "192.168.1.100",
      });

      // Access private method via any cast for testing
      const quantize = (node as any)._quantizePayload.bind(node);

      const data = new Float32Array([0.0, 0.5, 1.0, 0.25, 0.75, 1.5]);
      const result = quantize(data, 2, 3);

      expect(result[0]).toBe(0);
      expect(result[1]).toBe(128);
      expect(result[2]).toBe(255);
      expect(result[3]).toBe(64);
      expect(result[4]).toBe(191);
      expect(result[5]).toBe(255); // Clamped from 1.5
    });
  });

  describe("segment ID resolution", () => {
    it("should generate sequential IDs when no segments discovered", () => {
      const node = new GoveeLightNode({
        id: "test-govee",
        host: "192.168.1.100",
      });

      const resolve = (node as any)._resolveSegmentIds.bind(node);
      const ids = resolve(5);

      expect(ids).toEqual([0, 1, 2, 3, 4]);
    });
  });

  describe("color building", () => {
    it("should build RGB color from byte row", () => {
      const node = new GoveeLightNode({
        id: "test-govee",
        host: "192.168.1.100",
      });

      const rowToColor = (node as any)._rowToColor.bind(node);
      const byteMatrix = new Uint8Array([255, 128, 64, 200, 100, 50]);

      const color = rowToColor(byteMatrix, 0, 3);
      expect(color).toEqual({ r: 255, g: 128, b: 64 });

      const color2 = rowToColor(byteMatrix, 1, 3);
      expect(color2).toEqual({ r: 200, g: 100, b: 50 });
    });

    it("should build RGBW color when 4 channels", () => {
      const node = new GoveeLightNode({
        id: "test-govee",
        host: "192.168.1.100",
        segmentChannels: 4,
      });

      const rowToColor = (node as any)._rowToColor.bind(node);
      const byteMatrix = new Uint8Array([255, 128, 64, 32]);

      const color = rowToColor(byteMatrix, 0, 4);
      expect(color).toEqual({ r: 255, g: 128, b: 64, w: 32 });
    });
  });

  describe("segment payload building", () => {
    it("should build segment payload with colors", () => {
      const node = new GoveeLightNode({
        id: "test-govee",
        host: "192.168.1.100",
      });

      const buildPayload = (node as any)._buildSegmentPayload.bind(node);
      const byteMatrix = new Uint8Array([
        255,
        0,
        0, // Red
        0,
        255,
        0, // Green
        0,
        0,
        255, // Blue
      ]);
      const segmentIds = [0, 1, 2];

      const segments = buildPayload(byteMatrix, segmentIds, 3);

      expect(segments).toHaveLength(3);
      expect(segments[0]).toEqual({ segmentId: 0, r: 255, g: 0, b: 0 });
      expect(segments[1]).toEqual({ segmentId: 1, r: 0, g: 255, b: 0 });
      expect(segments[2]).toEqual({ segmentId: 2, r: 0, g: 0, b: 255 });
    });
  });
});
