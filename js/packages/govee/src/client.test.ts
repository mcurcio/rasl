import { describe, expect, it, vi } from "vitest";

import { DEFAULT_GOVEE_PORT, GoveeLightClient } from "./client.js";

describe("GoveeLightClient", () => {
  describe("constructor", () => {
    it("should use default port", () => {
      const client = new GoveeLightClient("192.168.1.100");
      expect(client.host).toBe("192.168.1.100");
      expect(client.port).toBe(DEFAULT_GOVEE_PORT);
    });

    it("should accept custom port", () => {
      const client = new GoveeLightClient("192.168.1.100", 5000);
      expect(client.port).toBe(5000);
    });

    it("should start with no error", () => {
      const client = new GoveeLightClient("192.168.1.100");
      expect(client.lastError).toBeNull();
    });

    it("should start disconnected", () => {
      const client = new GoveeLightClient("192.168.1.100");
      expect(client.isConnected).toBe(false);
    });
  });

  describe("close", () => {
    it("should be safe to call multiple times", () => {
      const client = new GoveeLightClient("192.168.1.100");
      client.close();
      client.close();
      expect(client.isConnected).toBe(false);
    });
  });

  describe("sendColorCommand", () => {
    it("should throw if no color or segments provided", () => {
      const client = new GoveeLightClient("192.168.1.100");
      expect(() => client.sendColorCommand(null)).toThrow("color or segments must be provided");
    });
  });
});

describe("parseSegments helper (via discover)", () => {
  it("should handle empty response", async () => {
    const client = new GoveeLightClient("192.168.1.100");
    // Mock queryStatus to return empty
    vi.spyOn(client, "queryStatus").mockResolvedValue({});
    const result = await client.discover();
    expect(result).toBeNull();
  });

  it("should parse segments from icSegments array", async () => {
    const client = new GoveeLightClient("192.168.1.100");
    vi.spyOn(client, "queryStatus").mockResolvedValue({
      msg: {
        cmd: "devStatus",
        data: {
          icSegments: [
            { segmentId: 0, count: 10 },
            { segmentId: 1, count: 20 },
          ],
        },
      },
    });
    const result = await client.discover();
    expect(result).not.toBeNull();
    expect(result!.segments).toHaveLength(2);
    expect(result!.segments[0].segmentId).toBe(0);
    expect(result!.segments[0].length).toBe(10);
    expect(result!.segments[1].segmentId).toBe(1);
    expect(result!.segments[1].length).toBe(20);
  });

  it("should parse segments from nested icSegments.segments", async () => {
    const client = new GoveeLightClient("192.168.1.100");
    vi.spyOn(client, "queryStatus").mockResolvedValue({
      msg: {
        cmd: "devStatus",
        data: {
          icSegments: {
            segments: [{ segmentId: 0, len: 15 }],
          },
        },
      },
    });
    const result = await client.discover();
    expect(result).not.toBeNull();
    expect(result!.segments).toHaveLength(1);
    expect(result!.segments[0].length).toBe(15);
  });

  it("should detect RGBW from color.w", async () => {
    const client = new GoveeLightClient("192.168.1.100");
    vi.spyOn(client, "queryStatus").mockResolvedValue({
      msg: {
        cmd: "devStatus",
        data: {
          color: { r: 255, g: 128, b: 64, w: 32 },
        },
      },
    });
    const result = await client.discover();
    expect(result).not.toBeNull();
    expect(result!.channelsPerSegment).toBe(4);
    expect(result!.supportsWhiteChannel).toBe(true);
  });

  it("should detect channels from channelCount hint", async () => {
    const client = new GoveeLightClient("192.168.1.100");
    vi.spyOn(client, "queryStatus").mockResolvedValue({
      msg: {
        cmd: "devStatus",
        data: {
          channelCount: 4,
        },
      },
    });
    const result = await client.discover();
    expect(result).not.toBeNull();
    expect(result!.channelsPerSegment).toBe(4);
  });

  it("should default to 3 channels (RGB)", async () => {
    const client = new GoveeLightClient("192.168.1.100");
    vi.spyOn(client, "queryStatus").mockResolvedValue({
      msg: {
        cmd: "devStatus",
        data: {},
      },
    });
    const result = await client.discover();
    expect(result).not.toBeNull();
    expect(result!.channelsPerSegment).toBe(3);
    expect(result!.supportsWhiteChannel).toBe(false);
  });
});
