/**
 * Tests for GraphBuilder.
 */

import { describe, expect, it } from "vitest";

import { BaseNode, InputPortSpec, OutputPortSpec, PortGroup } from "../runtime/index.js";
import type { ITickContext } from "../runtime/tick.js";
import { GraphBuilder } from "./builder.js";

// Type compatibility test nodes
class ColorSourceNode extends BaseNode {
  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "color" }),
  });
}

class ColorRgbSourceNode extends BaseNode {
  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "color:rgb" }),
  });
}

class BoolSourceNode extends BaseNode {
  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "bool" }),
  });
}

class MatrixSinkNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: "matrix" }),
  });
}

class ColorSinkNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: "color" }),
  });
}

class ColorRgbSinkNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: "color:rgb" }),
  });
}

class MultiAcceptSinkNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: ["color", "bool"] }),
  });
}

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

  describe("type compatibility validation", () => {
    describe("exact match", () => {
      it("should allow exact type match", () => {
        const builder = new GraphBuilder();
        builder.addNode(new ColorSourceNode({ id: "color" }));
        builder.addNode(new ColorSinkNode({ id: "sink" }));

        // color -> color: should work
        expect(() => {
          builder.connect("color", "out", "sink", "in");
        }).not.toThrow();
      });
    });

    describe("colon-prefix hierarchy", () => {
      it("should allow more specific type to less specific acceptor", () => {
        const builder = new GraphBuilder();
        builder.addNode(new ColorRgbSourceNode({ id: "rgb" }));
        builder.addNode(new ColorSinkNode({ id: "sink" }));

        // color:rgb -> color: should work (more specific is compatible)
        expect(() => {
          builder.connect("rgb", "out", "sink", "in");
        }).not.toThrow();
      });

      it("should reject less specific type to more specific acceptor", () => {
        const builder = new GraphBuilder();
        builder.addNode(new ColorSourceNode({ id: "color" }));
        builder.addNode(new ColorRgbSinkNode({ id: "sink" }));

        // color -> color:rgb: should fail (less specific cannot satisfy more specific)
        expect(() => {
          builder.connect("color", "out", "sink", "in");
        }).toThrow(/Type mismatch.*produces "color".*accepts "color:rgb"/);
      });
    });

    describe("inheritance hierarchy", () => {
      it("should allow color to matrix (color inherits from matrix)", () => {
        const builder = new GraphBuilder();
        builder.addNode(new ColorSourceNode({ id: "color" }));
        builder.addNode(new MatrixSinkNode({ id: "sink" }));

        // color -> matrix: should work (color inherits from matrix)
        expect(() => {
          builder.connect("color", "out", "sink", "in");
        }).not.toThrow();
      });

      it("should allow color:rgb to matrix (transitive inheritance)", () => {
        const builder = new GraphBuilder();
        builder.addNode(new ColorRgbSourceNode({ id: "rgb" }));
        builder.addNode(new MatrixSinkNode({ id: "sink" }));

        // color:rgb -> matrix: should work (color:rgb -> color -> matrix)
        expect(() => {
          builder.connect("rgb", "out", "sink", "in");
        }).not.toThrow();
      });

      it("should allow bool to matrix (bool inherits from matrix)", () => {
        const builder = new GraphBuilder();
        builder.addNode(new BoolSourceNode({ id: "bool" }));
        builder.addNode(new MatrixSinkNode({ id: "sink" }));

        // bool -> matrix: should work
        expect(() => {
          builder.connect("bool", "out", "sink", "in");
        }).not.toThrow();
      });

      it("should reject matrix to color (parent cannot satisfy child)", () => {
        const builder = new GraphBuilder();
        builder.addNode(new TestSourceNode({ id: "matrix" })); // produces "matrix"
        builder.addNode(new ColorSinkNode({ id: "sink" }));

        // matrix -> color: should fail
        expect(() => {
          builder.connect("matrix", "out", "sink", "in");
        }).toThrow(/Type mismatch.*produces "matrix".*accepts "color"/);
      });

      it("should reject bool to color (siblings)", () => {
        const builder = new GraphBuilder();
        builder.addNode(new BoolSourceNode({ id: "bool" }));
        builder.addNode(new ColorSinkNode({ id: "sink" }));

        // bool -> color: should fail (both inherit from matrix, but not from each other)
        expect(() => {
          builder.connect("bool", "out", "sink", "in");
        }).toThrow(/Type mismatch.*produces "bool".*accepts "color"/);
      });
    });

    describe("multi-accept ports", () => {
      it("should allow any matching type from accepts array", () => {
        const builder = new GraphBuilder();
        builder.addNode(new ColorSourceNode({ id: "color" }));
        builder.addNode(new BoolSourceNode({ id: "bool" }));
        builder.addNode(new MultiAcceptSinkNode({ id: "sink1" }));
        builder.addNode(new MultiAcceptSinkNode({ id: "sink2" }));

        // color -> [color, bool]: should work
        expect(() => {
          builder.connect("color", "out", "sink1", "in");
        }).not.toThrow();

        // bool -> [color, bool]: should work
        expect(() => {
          builder.connect("bool", "out", "sink2", "in");
        }).not.toThrow();
      });

      it("should allow subtype to multi-accept port", () => {
        const builder = new GraphBuilder();
        builder.addNode(new ColorRgbSourceNode({ id: "rgb" }));
        builder.addNode(new MultiAcceptSinkNode({ id: "sink" }));

        // color:rgb -> [color, bool]: should work (color:rgb is subtype of color)
        expect(() => {
          builder.connect("rgb", "out", "sink", "in");
        }).not.toThrow();
      });

      it("should reject incompatible type to multi-accept port", () => {
        const builder = new GraphBuilder();
        builder.addNode(new TestSourceNode({ id: "matrix" })); // produces "matrix"
        builder.addNode(new MultiAcceptSinkNode({ id: "sink" }));

        // matrix -> [color, bool]: should fail (matrix is parent, not child)
        expect(() => {
          builder.connect("matrix", "out", "sink", "in");
        }).toThrow(/Type mismatch.*produces "matrix".*accepts "color \| bool"/);
      });
    });
  });
});
