/**
 * Tests for RaslServer HTTP implementation.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { createEngineLogger } from "@rasl/engine";
import { RaslServer } from "./server.js";
import type { UnifiedScheduler } from "@rasl/engine";

function createMockScheduler(nodes: Map<string, unknown> = new Map()) {
  const stats = new Map<string, unknown>();
  return {
    _plan: {
      nodes,
      describe: () => ({
        nodes: Array.from(nodes.entries()).map(([id, n]) => ({
          id,
          type: (n as { constructor: { name: string } }).constructor.name,
          inputs: [],
          outputs: [],
        })),
        edges: [],
        topologicalOrder: Array.from(nodes.keys()),
      }),
    },
    getNodeStats: (nodeId?: string) => {
      if (nodeId !== undefined) {
        return stats.get(nodeId) ?? null;
      }
      return stats;
    },
  };
}

describe("RaslServer", () => {
  let server: RaslServer;
  const TEST_PORT = 19876; // Use high port to avoid conflicts

  beforeEach(() => {
    server = new RaslServer({ port: TEST_PORT, host: "127.0.0.1", logger: createEngineLogger({ level: "error" }) });
  });

  afterEach(async () => {
    if (server.isRunning) {
      await server.stop();
    }
  });

  describe("lifecycle", () => {
    it("should start and stop cleanly", async () => {
      const scheduler = createMockScheduler();
      expect(server.isRunning).toBe(false);

      await server.start(scheduler as never);
      expect(server.isRunning).toBe(true);
      expect(server.url).toBe(`http://127.0.0.1:${TEST_PORT}`);

      await server.stop();
      expect(server.isRunning).toBe(false);
    });

    it("should not start twice", async () => {
      const scheduler = createMockScheduler();
      await server.start(scheduler as never);
      await server.start(scheduler as never); // Should be no-op
      expect(server.isRunning).toBe(true);
    });

    it("should handle stop when not running", async () => {
      await server.stop(); // Should be no-op
      expect(server.isRunning).toBe(false);
    });
  });

  describe("GET /health", () => {
    it("should return health status", async () => {
      const scheduler = createMockScheduler();
      await server.start(scheduler as never);

      const res = await fetch(`http://127.0.0.1:${TEST_PORT}/health`);
      expect(res.status).toBe(200);

      const body = await res.json();
      expect(body.status).toBe("ok");
      expect(body.version).toBe("0.1.0");
      expect(typeof body.uptime).toBe("number");
      expect(body.uptime).toBeGreaterThanOrEqual(0);
    });
  });

  describe("GET /graph", () => {
    it("should return graph description", async () => {
      const nodes = new Map<string, unknown>();
      nodes.set("testNode", { id: "testNode", constructor: { name: "TestNode" } });

      const scheduler = createMockScheduler(nodes);
      await server.start(scheduler as never);

      const res = await fetch(`http://127.0.0.1:${TEST_PORT}/graph`);
      expect(res.status).toBe(200);

      const body = await res.json();
      expect(body.graph).toBeDefined();
      expect(body.graph.nodes).toHaveLength(1);
      expect(body.graph.nodes[0].id).toBe("testNode");
      expect(body.graph.topologicalOrder).toContain("testNode");
    });
  });

  describe("GET /stats", () => {
    it("should return execution statistics", async () => {
      const scheduler = createMockScheduler();
      await server.start(scheduler as never);

      const res = await fetch(`http://127.0.0.1:${TEST_PORT}/stats`);
      expect(res.status).toBe(200);

      const body = await res.json();
      expect(body.running).toBe(true);
      expect(typeof body.uptime).toBe("number");
      expect(body.nodes).toBeDefined();
    });
  });

  describe("GET /node/:id", () => {
    it("should return node details", async () => {
      const nodes = new Map<string, unknown>();
      nodes.set("myNode", {
        id: "myNode",
        constructor: { name: "WaveformNode" },
        inputs: { names: ["phase", "speed"] },
        outputs: { names: ["out"] },
      });

      const scheduler = createMockScheduler(nodes);
      await server.start(scheduler as never);

      const res = await fetch(`http://127.0.0.1:${TEST_PORT}/node/myNode`);
      expect(res.status).toBe(200);

      const body = await res.json();
      expect(body.id).toBe("myNode");
      expect(body.type).toBe("WaveformNode");
      expect(body.inputs).toEqual(["phase", "speed"]);
      expect(body.outputs).toEqual(["out"]);
    });

    it("should return 404 for unknown node", async () => {
      const scheduler = createMockScheduler();
      await server.start(scheduler as never);

      const res = await fetch(`http://127.0.0.1:${TEST_PORT}/node/unknown`);
      expect(res.status).toBe(404);

      const body = await res.json();
      expect(body.error).toContain("not found");
    });
  });

  describe("error handling", () => {
    it("should return 404 for unknown routes", async () => {
      const scheduler = createMockScheduler();
      await server.start(scheduler as never);

      const res = await fetch(`http://127.0.0.1:${TEST_PORT}/unknown`);
      expect(res.status).toBe(404);
    });

    it("should return 405 for non-GET methods", async () => {
      const scheduler = createMockScheduler();
      await server.start(scheduler as never);

      const res = await fetch(`http://127.0.0.1:${TEST_PORT}/health`, {
        method: "POST",
      });
      expect(res.status).toBe(405);
    });
  });

  describe("CORS", () => {
    it("should include CORS headers", async () => {
      const scheduler = createMockScheduler();
      await server.start(scheduler as never);

      const res = await fetch(`http://127.0.0.1:${TEST_PORT}/health`);
      expect(res.headers.get("Access-Control-Allow-Origin")).toBe("*");
    });

    it("should handle OPTIONS preflight", async () => {
      const scheduler = createMockScheduler();
      await server.start(scheduler as never);

      const res = await fetch(`http://127.0.0.1:${TEST_PORT}/health`, {
        method: "OPTIONS",
      });
      expect(res.status).toBe(204);
    });
  });
});
