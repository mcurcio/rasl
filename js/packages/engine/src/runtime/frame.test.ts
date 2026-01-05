/**
 * Tests for Frame and related types.
 */

import { describe, expect,it } from "vitest";

import { EMPTY_METADATA,Frame } from "./frame.js";
import { BoolPayload,MatrixPayload } from "./payloads/index.js";

describe("Frame", () => {
  describe("construction", () => {
    it("should create a frame with required fields", () => {
      const payload = new MatrixPayload([1, 2, 3]);
      const frame = new Frame({
        topic: "test",
        timestamp: 1.5,
        payload,
      });

      expect(frame.topic).toBe("test");
      expect(frame.timestamp).toBe(1.5);
      expect(frame.payload).toBe(payload);
      expect(frame.metadata).toBe(EMPTY_METADATA);
    });

    it("should create a frame with metadata", () => {
      const payload = new MatrixPayload([1]);
      const frame = new Frame({
        topic: "test",
        timestamp: 0,
        payload,
        metadata: { source: "unit-test" },
      });

      expect(frame.metadata).toEqual({ source: "unit-test" });
    });
  });

  describe("withPayload", () => {
    it("should create new frame with different payload", () => {
      const payload1 = new MatrixPayload([1, 2, 3]);
      const payload2 = new MatrixPayload([4, 5, 6]);
      const frame1 = new Frame({
        topic: "test",
        timestamp: 1.0,
        payload: payload1,
        metadata: { key: "value" },
      });

      const frame2 = frame1.withPayload(payload2);

      expect(frame2.topic).toBe("test");
      expect(frame2.timestamp).toBe(1.0);
      expect(frame2.payload).toBe(payload2);
      expect(frame2.metadata).toEqual({ key: "value" });
      expect(frame1.payload).toBe(payload1); // Original unchanged
    });
  });

  describe("withMetadata", () => {
    it("should create new frame with merged metadata", () => {
      const payload = new MatrixPayload([1]);
      const frame1 = new Frame({
        topic: "test",
        timestamp: 0,
        payload,
        metadata: { a: "1" },
      });

      const frame2 = frame1.withMetadata({ b: "2" });

      expect(frame2.metadata).toEqual({ a: "1", b: "2" });
      expect(frame1.metadata).toEqual({ a: "1" }); // Original unchanged
    });

    it("should override existing metadata keys", () => {
      const payload = new MatrixPayload([1]);
      const frame1 = new Frame({
        topic: "test",
        timestamp: 0,
        payload,
        metadata: { a: "1" },
      });

      const frame2 = frame1.withMetadata({ a: "updated" });

      expect(frame2.metadata).toEqual({ a: "updated" });
    });
  });
});

describe("MatrixPayload", () => {
  describe("construction", () => {
    it("should create from Float32Array", () => {
      const data = new Float32Array([1, 2, 3, 4, 5, 6]);
      const payload = new MatrixPayload(data, 3);

      expect(payload.count).toBe(2);
      expect(payload.channels).toBe(3);
      expect(payload.size).toBe(6);
    });

    it("should create from number array", () => {
      const payload = new MatrixPayload([1, 2, 3, 4], 2);

      expect(payload.count).toBe(2);
      expect(payload.channels).toBe(2);
      expect(payload.data).toBeInstanceOf(Float32Array);
    });

    it("should default to 1 channel", () => {
      const payload = new MatrixPayload([1, 2, 3]);

      expect(payload.count).toBe(3);
      expect(payload.channels).toBe(1);
    });

    it("should throw for invalid channels", () => {
      expect(() => new MatrixPayload([1, 2, 3], 0)).toThrow("channels must be >= 1");
      expect(() => new MatrixPayload([1, 2, 3], -1)).toThrow("channels must be >= 1");
    });
  });

  describe("get", () => {
    it("should get value at row/col", () => {
      const payload = new MatrixPayload([1, 2, 3, 4, 5, 6], 3);

      expect(payload.get(0, 0)).toBe(1);
      expect(payload.get(0, 1)).toBe(2);
      expect(payload.get(0, 2)).toBe(3);
      expect(payload.get(1, 0)).toBe(4);
      expect(payload.get(1, 1)).toBe(5);
      expect(payload.get(1, 2)).toBe(6);
    });

    it("should default col to 0", () => {
      const payload = new MatrixPayload([1, 2, 3]);
      expect(payload.get(1)).toBe(2);
    });
  });

  describe("getRow", () => {
    it("should return row as subarray view", () => {
      const payload = new MatrixPayload([1, 2, 3, 4, 5, 6], 3);

      const row0 = payload.getRow(0);
      const row1 = payload.getRow(1);

      expect(Array.from(row0)).toEqual([1, 2, 3]);
      expect(Array.from(row1)).toEqual([4, 5, 6]);
    });
  });

  describe("repeat", () => {
    it("should repeat payload n times", () => {
      const payload = new MatrixPayload([1, 2, 3], 3);
      const repeated = payload.repeat(3);

      expect(repeated.count).toBe(3);
      expect(repeated.channels).toBe(3);
      expect(Array.from(repeated.data)).toEqual([1, 2, 3, 1, 2, 3, 1, 2, 3]);
    });

    it("should return same payload for n <= 1", () => {
      const payload = new MatrixPayload([1, 2, 3]);

      expect(payload.repeat(1)).toBe(payload);
      expect(payload.repeat(0)).toBe(payload);
    });
  });

  describe("describe", () => {
    it("should return descriptor", () => {
      const payload = new MatrixPayload([1, 2, 3, 4], 2);
      const desc = payload.describe();

      expect(desc.typeName).toBe("MatrixPayload");
      expect(desc.domain).toBe("matrix");
      expect(desc.attrs.count).toBe(2);
      expect(desc.attrs.channels).toBe(2);
      expect(desc.attrs.size).toBe(4);
    });
  });

  describe("isCompatibleWith", () => {
    it("should accept MatrixPayload", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect(MatrixPayload.isCompatibleWith(MatrixPayload as any)).toBe(true);
    });

    it("should accept BoolPayload (subclass)", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect(MatrixPayload.isCompatibleWith(BoolPayload as any)).toBe(true);
    });
  });
});

describe("BoolPayload", () => {
  describe("construction", () => {
    it("should normalize boolean array to 0/1", () => {
      const payload = new BoolPayload([true, false, true, false]);

      expect(payload.count).toBe(4);
      expect(payload.channels).toBe(1);
      expect(Array.from(payload.data)).toEqual([1, 0, 1, 0]);
    });

    it("should normalize number array to 0/1", () => {
      const payload = new BoolPayload([0, 1, 2, -1, 0.5]);

      expect(Array.from(payload.data)).toEqual([0, 1, 1, 1, 1]);
    });

    it("should normalize Float32Array to 0/1", () => {
      const payload = new BoolPayload(new Float32Array([0, 0.5, 1, -1]));

      expect(Array.from(payload.data)).toEqual([0, 1, 1, 1]);
    });
  });

  describe("describe", () => {
    it("should return descriptor with bool domain", () => {
      const payload = new BoolPayload([true, false]);
      const desc = payload.describe();

      expect(desc.typeName).toBe("BoolPayload");
      expect(desc.domain).toBe("bool");
    });
  });
});
