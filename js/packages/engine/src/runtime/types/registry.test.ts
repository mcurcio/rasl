/**
 * Tests for TypeRegistry - payload type compatibility resolver.
 */

import { describe, expect, it, beforeEach } from "vitest";

import { TypeRegistry, isTypeCompatible, globalTypeRegistry } from "./registry.js";

describe("TypeRegistry", () => {
  let registry: TypeRegistry;

  beforeEach(() => {
    registry = new TypeRegistry();
  });

  describe("exact match", () => {
    it("should match identical types", () => {
      expect(registry.isCompatible("matrix", "matrix")).toBe(true);
      expect(registry.isCompatible("color", "color")).toBe(true);
      expect(registry.isCompatible("bool", "bool")).toBe(true);
    });

    it("should not match different types without inheritance", () => {
      expect(registry.isCompatible("color", "bool")).toBe(false);
      expect(registry.isCompatible("matrix", "color")).toBe(false);
    });
  });

  describe("colon-prefix hierarchy", () => {
    it("should match more specific type to less specific acceptor", () => {
      // "color:rgb" produces, "color" accepts -> compatible
      expect(registry.isCompatible("color:rgb", "color")).toBe(true);
    });

    it("should match deeply nested types", () => {
      // "color:rgb:linear" is compatible with "color:rgb" and "color"
      expect(registry.isCompatible("color:rgb:linear", "color:rgb")).toBe(true);
      expect(registry.isCompatible("color:rgb:linear", "color")).toBe(true);
    });

    it("should not match less specific type to more specific acceptor", () => {
      // "color" produces, "color:rgb" accepts -> NOT compatible
      expect(registry.isCompatible("color", "color:rgb")).toBe(false);
    });

    it("should not match partial string prefixes", () => {
      // "colorful" is NOT a subtype of "color"
      expect(registry.isCompatible("colorful", "color")).toBe(false);
    });

    it("should handle single-segment types", () => {
      expect(registry.isCompatible("matrix", "matrix")).toBe(true);
      expect(registry.isCompatible("matrix", "mat")).toBe(false);
    });
  });

  describe("registerInheritance", () => {
    it("should register direct inheritance", () => {
      registry.registerInheritance("color", "matrix");

      expect(registry.isCompatible("color", "matrix")).toBe(true);
    });

    it("should support transitive inheritance", () => {
      registry.registerInheritance("color:rgb", "color");
      registry.registerInheritance("color", "matrix");

      // color:rgb -> color -> matrix
      expect(registry.isCompatible("color:rgb", "matrix")).toBe(true);
    });

    it("should throw on self-inheritance", () => {
      expect(() => {
        registry.registerInheritance("color", "color");
      }).toThrow("Cannot register self-inheritance");
    });

    it("should throw on cycle detection", () => {
      registry.registerInheritance("a", "b");
      registry.registerInheritance("b", "c");

      expect(() => {
        registry.registerInheritance("c", "a");
      }).toThrow("cycle");
    });

    it("should allow multiple parents", () => {
      registry.registerInheritance("color", "matrix");
      registry.registerInheritance("color", "displayable");

      expect(registry.isCompatible("color", "matrix")).toBe(true);
      expect(registry.isCompatible("color", "displayable")).toBe(true);
    });
  });

  describe("getParents", () => {
    it("should return empty array for types with no inheritance", () => {
      expect(registry.getParents("matrix")).toEqual([]);
    });

    it("should return direct parents", () => {
      registry.registerInheritance("color", "matrix");

      const parents = registry.getParents("color");
      expect(parents).toContain("matrix");
    });

    it("should return transitive parents", () => {
      registry.registerInheritance("color:rgb", "color");
      registry.registerInheritance("color", "matrix");

      const parents = registry.getParents("color:rgb");
      expect(parents).toContain("color");
      expect(parents).toContain("matrix");
    });
  });

  describe("combined hierarchy and inheritance", () => {
    it("should combine colon-prefix with inheritance", () => {
      registry.registerInheritance("color", "matrix");

      // "color:rgb:linear" should be compatible with "matrix"
      // because "color:rgb:linear" -> "color" (prefix) -> "matrix" (inheritance)
      expect(registry.isCompatible("color:rgb:linear", "matrix")).toBe(true);
    });

    it("should handle complex hierarchies", () => {
      registry.registerInheritance("color", "matrix");
      registry.registerInheritance("bool", "matrix");

      // color:oklch:hdr is compatible with matrix
      expect(registry.isCompatible("color:oklch:hdr", "matrix")).toBe(true);

      // bool is compatible with matrix
      expect(registry.isCompatible("bool", "matrix")).toBe(true);

      // color is NOT compatible with bool
      expect(registry.isCompatible("color", "bool")).toBe(false);
    });
  });
});

describe("isTypeCompatible (global registry)", () => {
  it("should use global registry with default types", () => {
    // Default types register color -> matrix and bool -> matrix
    expect(isTypeCompatible("color", "matrix")).toBe(true);
    expect(isTypeCompatible("bool", "matrix")).toBe(true);
  });

  it("should support colon-prefix hierarchy", () => {
    expect(isTypeCompatible("color:rgb", "color")).toBe(true);
    expect(isTypeCompatible("color:rgb:linear", "matrix")).toBe(true);
  });
});

describe("globalTypeRegistry default types", () => {
  it("should have color inheriting from matrix", () => {
    expect(globalTypeRegistry.isCompatible("color", "matrix")).toBe(true);
  });

  it("should have bool inheriting from matrix", () => {
    expect(globalTypeRegistry.isCompatible("bool", "matrix")).toBe(true);
  });

  it("should support color subtypes inheriting matrix", () => {
    expect(globalTypeRegistry.isCompatible("color:rgb", "matrix")).toBe(true);
    expect(globalTypeRegistry.isCompatible("color:oklch", "matrix")).toBe(true);
  });
});

describe("negative compatibility cases", () => {
  let registry: TypeRegistry;

  beforeEach(() => {
    registry = new TypeRegistry();
    registry.registerInheritance("color", "matrix");
    registry.registerInheritance("bool", "matrix");
  });

  it("should reject incompatible types", () => {
    // matrix does NOT satisfy color (less specific cannot satisfy more specific)
    expect(registry.isCompatible("matrix", "color")).toBe(false);

    // bool does NOT satisfy color (siblings)
    expect(registry.isCompatible("bool", "color")).toBe(false);

    // color does NOT satisfy bool (siblings)
    expect(registry.isCompatible("color", "bool")).toBe(false);
  });

  it("should reject unrelated types", () => {
    expect(registry.isCompatible("audio", "color")).toBe(false);
    expect(registry.isCompatible("color", "audio")).toBe(false);
  });

  it("should reject partial string matches", () => {
    // "mat" is not a valid prefix of "matrix"
    expect(registry.isCompatible("matrix", "mat")).toBe(false);

    // "matrixlike" is not related to "matrix"
    expect(registry.isCompatible("matrixlike", "matrix")).toBe(false);
  });
});
