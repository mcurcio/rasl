/**
 * Tests for GraphBuilder.
 */

import { describe, expect, it } from "vitest";

import { BaseNode, InputPortSpec, OutputPortSpec, PortGroup } from "../runtime/index.js";
import type { ITickContext } from "../runtime/tick.js";
import { GraphBuilder } from "./builder.js";

// Test node implementations
class TestSourceNode extends BaseNode {
  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "matrix", count: 1 }),
  });

  override async pull(_tick: ITickContext): Promise<void> {
    // No-op for testing
  }
}

class TestTransformNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: "matrix", count: 1 }),
  });
  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "matrix", count: 1 }),
  });

  override async pull(_tick: ITickContext): Promise<void> {
    // No-op for testing
  }
}

class TestSinkNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: "matrix", count: 1 }),
  });

  override async pull(_tick: ITickContext): Promise<void> {
    // No-op for testing
  }
}

describe("GraphBuilder", () => {
  describe("addNode", () => {
    it("should add a node", () => {
      const builder = new GraphBuilder();
      const node = new TestSourceNode({ id: "source" });

      builder.addNode(node);

      expect(builder.nodes.has("source")).toBe(true);
      expect(builder.nodes.get("source")).toBe(node);
    });

    it("should throw on duplicate node id", () => {
      const builder = new GraphBuilder();
      builder.addNode(new TestSourceNode({ id: "source" }));

      expect(() => {
        builder.addNode(new TestSourceNode({ id: "source" }));
      }).toThrow("Duplicate node id 'source'");
    });
  });

  describe("connect", () => {
    it("should connect two nodes", () => {
      const builder = new GraphBuilder();
      builder.addNode(new TestSourceNode({ id: "source" }));
      builder.addNode(new TestSinkNode({ id: "sink" }));

      builder.connect("source", "out", "sink", "in");

      expect(builder.edges).toHaveLength(1);
      expect(builder.edges[0].source).toBe("source");
      expect(builder.edges[0].sourcePort).toBe("out");
      expect(builder.edges[0].target).toBe("sink");
      expect(builder.edges[0].targetPort).toBe("in");
    });

    it("should throw for unknown source node", () => {
      const builder = new GraphBuilder();
      builder.addNode(new TestSinkNode({ id: "sink" }));

      expect(() => {
        builder.connect("unknown", "out", "sink", "in");
      }).toThrow("Unknown source node 'unknown'");
    });

    it("should throw for unknown target node", () => {
      const builder = new GraphBuilder();
      builder.addNode(new TestSourceNode({ id: "source" }));

      expect(() => {
        builder.connect("source", "out", "unknown", "in");
      }).toThrow("Unknown target node 'unknown'");
    });

    it("should throw for unknown source port", () => {
      const builder = new GraphBuilder();
      builder.addNode(new TestSourceNode({ id: "source" }));
      builder.addNode(new TestSinkNode({ id: "sink" }));

      expect(() => {
        builder.connect("source", "badport", "sink", "in");
      }).toThrow("has no output port 'badport'");
    });

    it("should throw for unknown target port", () => {
      const builder = new GraphBuilder();
      builder.addNode(new TestSourceNode({ id: "source" }));
      builder.addNode(new TestSinkNode({ id: "sink" }));

      expect(() => {
        builder.connect("source", "out", "sink", "badport");
      }).toThrow("has no input port 'badport'");
    });
  });

  describe("connectDefault", () => {
    it("should connect default ports", () => {
      const builder = new GraphBuilder();
      builder.addNode(new TestSourceNode({ id: "source" }));
      builder.addNode(new TestSinkNode({ id: "sink" }));

      builder.connectDefault("source", "sink");

      expect(builder.edges).toHaveLength(1);
      expect(builder.edges[0].sourcePort).toBe("out");
      expect(builder.edges[0].targetPort).toBe("in");
    });
  });

  describe("build", () => {
    it("should build execution plan", () => {
      const builder = new GraphBuilder();
      builder.addNode(new TestSourceNode({ id: "source" }));
      builder.addNode(new TestTransformNode({ id: "transform" }));
      builder.addNode(new TestSinkNode({ id: "sink" }));
      builder.connect("source", "out", "transform", "in");
      builder.connect("transform", "out", "sink", "in");

      const plan = builder.build();

      expect(plan.nodes.size).toBe(3);
      expect(plan.topologicalOrder).toContain("source");
      expect(plan.topologicalOrder).toContain("transform");
      expect(plan.topologicalOrder).toContain("sink");
    });

    it("should order nodes topologically", () => {
      const builder = new GraphBuilder();
      // Add in reverse order
      builder.addNode(new TestSinkNode({ id: "sink" }));
      builder.addNode(new TestTransformNode({ id: "transform" }));
      builder.addNode(new TestSourceNode({ id: "source" }));
      builder.connect("source", "out", "transform", "in");
      builder.connect("transform", "out", "sink", "in");

      const plan = builder.build();

      const sourceIdx = plan.topologicalOrder.indexOf("source");
      const transformIdx = plan.topologicalOrder.indexOf("transform");
      const sinkIdx = plan.topologicalOrder.indexOf("sink");

      expect(sourceIdx).toBeLessThan(transformIdx);
      expect(transformIdx).toBeLessThan(sinkIdx);
    });

    it("should handle disconnected nodes", () => {
      const builder = new GraphBuilder();
      builder.addNode(new TestSourceNode({ id: "source1" }));
      builder.addNode(new TestSourceNode({ id: "source2" }));

      const plan = builder.build();

      expect(plan.nodes.size).toBe(2);
      expect(plan.topologicalOrder).toHaveLength(2);
    });

    it("should handle cycles gracefully", () => {
      const builder = new GraphBuilder();

      // Create nodes that can form a cycle
      class CyclicNode extends BaseNode {
        readonly inputs = PortGroup.inputs({
          in: new InputPortSpec({ accepts: "matrix" }),
        });
        readonly outputs = PortGroup.outputs({
          out: new OutputPortSpec({ produces: "matrix" }),
        });
      }

      builder.addNode(new CyclicNode({ id: "a" }));
      builder.addNode(new CyclicNode({ id: "b" }));
      builder.connect("a", "out", "b", "in");
      builder.connect("b", "out", "a", "in");

      // Should not throw, but should warn (cycles are allowed)
      const plan = builder.build();
      expect(plan.nodes.size).toBe(2);
    });
  });

  describe("describe", () => {
    it("should serialize graph to description", () => {
      const builder = new GraphBuilder();
      builder.addNode(new TestSourceNode({ id: "source" }));
      builder.addNode(new TestSinkNode({ id: "sink" }));
      builder.connect("source", "out", "sink", "in");

      const plan = builder.build();
      const desc = plan.describe();

      expect(desc.nodes).toHaveLength(2);
      expect(desc.edges).toHaveLength(1);
      expect(desc.topologicalOrder).toHaveLength(2);

      const sourceNode = desc.nodes.find((n) => n.id === "source");
      expect(sourceNode?.type).toBe("TestSourceNode");
      expect(sourceNode?.outputs).toContain("out");

      const edge = desc.edges[0];
      expect(edge.source).toBe("source");
      expect(edge.target).toBe("sink");
    });
  });
});
