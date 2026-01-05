import { describe, expect,it } from "vitest";

import { LifxSinkNode } from "./node.js";

describe("LifxSinkNode", () => {
  describe("constructor", () => {
    it("should create with required config", () => {
      const node = new LifxSinkNode({
        id: "test-lifx",
        target: "192.168.1.100",
      });
      expect(node.id).toBe("test-lifx");
      expect(node.inputs.get("color")).toBeDefined();
    });

    it("should accept multiple targets", () => {
      const node = new LifxSinkNode({
        id: "test-lifx",
        target: "192.168.1.100, 192.168.1.101",
      });
      expect(node).toBeDefined();
    });

    it("should throw if no targets provided", () => {
      expect(
        () =>
          new LifxSinkNode({
            id: "test-lifx",
            target: "",
          }),
      ).toThrow("at least one IP address");
    });

    it("should parse fps from number", () => {
      const node = new LifxSinkNode({
        id: "test-lifx",
        target: "192.168.1.100",
        fps: 60,
      });
      expect(node).toBeDefined();
    });

    it("should parse fps from hz string", () => {
      const node = new LifxSinkNode({
        id: "test-lifx",
        target: "192.168.1.100",
        fps: "30hz",
      });
      expect(node).toBeDefined();
    });

    it("should parse fps from ms string", () => {
      const node = new LifxSinkNode({
        id: "test-lifx",
        target: "192.168.1.100",
        fps: "33ms",
      });
      expect(node).toBeDefined();
    });
  });

  describe("assignment building", () => {
    it("should build 1:1 assignments when rows match clients", () => {
      const node = new LifxSinkNode({
        id: "test-lifx",
        target: "192.168.1.100, 192.168.1.101, 192.168.1.102",
      });

      const buildAssignments = (node as any)._buildAssignments.bind(node);
      const assignments = buildAssignments(3, 3);

      expect(assignments).toHaveLength(3);
      expect(assignments[0]).toEqual([0, 0]);
      expect(assignments[1]).toEqual([1, 1]);
      expect(assignments[2]).toEqual([2, 2]);
    });

    it("should broadcast single row to all clients", () => {
      const node = new LifxSinkNode({
        id: "test-lifx",
        target: "192.168.1.100, 192.168.1.101",
      });

      const buildAssignments = (node as any)._buildAssignments.bind(node);
      const assignments = buildAssignments(1, 2);

      expect(assignments).toHaveLength(2);
      expect(assignments[0]).toEqual([0, 0]);
      expect(assignments[1]).toEqual([1, 0]);
    });

    it("should use first row for single client", () => {
      const node = new LifxSinkNode({
        id: "test-lifx",
        target: "192.168.1.100",
      });

      const buildAssignments = (node as any)._buildAssignments.bind(node);
      const assignments = buildAssignments(5, 1);

      expect(assignments).toHaveLength(1);
      expect(assignments[0]).toEqual([0, 0]);
    });

    it("should return empty on mismatch", () => {
      const node = new LifxSinkNode({
        id: "test-lifx",
        target: "192.168.1.100, 192.168.1.101",
      });

      const buildAssignments = (node as any)._buildAssignments.bind(node);
      const assignments = buildAssignments(3, 2);

      expect(assignments).toHaveLength(0);
    });

    it("should return empty when no rows", () => {
      const node = new LifxSinkNode({
        id: "test-lifx",
        target: "192.168.1.100",
      });

      const buildAssignments = (node as any)._buildAssignments.bind(node);
      const assignments = buildAssignments(0, 1);

      expect(assignments).toHaveLength(0);
    });

    it("should return empty when no clients", () => {
      const node = new LifxSinkNode({
        id: "test-lifx",
        target: "192.168.1.100",
      });

      const buildAssignments = (node as any)._buildAssignments.bind(node);
      const assignments = buildAssignments(3, 0);

      expect(assignments).toHaveLength(0);
    });
  });
});
