/**
 * Tests for async include resolution.
 */

import { describe, expect, it } from "vitest";

import { type DocumentLoader, parse } from "./index.js";
import { DiagnosticCode } from "./tokens.js";

describe("Include Resolution", () => {
  describe("basic includes", () => {
    it("should throw if loader is missing", async () => {
      await expect(parse("listen 8080;", undefined as unknown as never)).rejects.toThrow(/loader is required/);
    });

    it("should resolve single include", async () => {
      const files: Record<string, string> = {
        "other.conf": "listen 8080;",
      };

      const loader: DocumentLoader = async (spec) => {
        const content = files[spec];
        if (!content) return [];
        return [{ source: content, resolvedPath: spec }];
      };

      const source = 'include "other.conf";';
      const result = await parse(source, {
        path: "/root/root.conf",
        loader,
      });

      const includeDir = result.root.parseResult.cst.children[0]!;
      const edge = result.root.includes.get(includeDir)!;
      expect(edge.targets).toHaveLength(1);
      expect(edge.targets[0].ast.children.length).toBe(1);
    });

    it("should resolve nested includes", async () => {
      const files: Record<string, string> = {
        "a.conf": 'include "b.conf";',
        "b.conf": "listen 8080;",
      };

      const loader: DocumentLoader = async (spec) => {
        const content = files[spec];
        if (!content) return [];
        return [{ source: content, resolvedPath: spec }];
      };

      const source = 'include "a.conf";';
      const result = await parse(source, {
        path: "/root/root.conf",
        loader,
      });

      expect(result.nodes.size).toBe(3); // root + a.conf + b.conf
    });
  });

  describe("glob support", () => {
    it("should resolve multiple files from glob", async () => {
      const loader: DocumentLoader = async (spec) => {
        if (spec === "*.conf") {
          return [
            { source: "a 1;", resolvedPath: "a.conf" },
            { source: "b 2;", resolvedPath: "b.conf" },
            { source: "c 3;", resolvedPath: "c.conf" },
          ];
        }
        return [];
      };

      const source = 'include "*.conf";';
      const result = await parse(source, {
        path: "/root/root.conf",
        loader,
      });

      const includeDir = result.root.parseResult.cst.children[0]!;
      const edge = result.root.includes.get(includeDir)!;
      expect(edge.targets).toHaveLength(3);
    });

    it("should sort glob matches by resolved path", async () => {
      const loader: DocumentLoader = async (spec) => {
        if (spec === "*.conf") {
          // Return in non-sorted order
          return [
            { source: "c 3;", resolvedPath: "c.conf" },
            { source: "a 1;", resolvedPath: "a.conf" },
            { source: "b 2;", resolvedPath: "b.conf" },
          ];
        }
        return [];
      };

      const source = 'include "*.conf";';
      const result = await parse(source, {
        path: "/root/root.conf",
        loader,
      });

      const includeDir = result.root.parseResult.cst.children[0]!;
      const edge = result.root.includes.get(includeDir)!;
      const paths = edge.targets.map((t) => t.resolvedPath);
      expect(paths).toEqual(["a.conf", "b.conf", "c.conf"]);
    });

    it("should error on no glob matches", async () => {
      const loader: DocumentLoader = async () => [];

      const source = 'include "*.conf";';
      const result = await parse(source, {
        path: "/root/root.conf",
        loader,
      });

      const errors = result.diagnostics.filter((d) => d.code === DiagnosticCode.IncludeNotFound);
      expect(errors).toHaveLength(1);
    });
  });

  describe("cycle detection", () => {
    it("should detect direct cycle", async () => {
      const loader: DocumentLoader = async (spec) => {
        if (spec === "self.conf") {
          return [{ source: 'include "self.conf";', resolvedPath: "self.conf" }];
        }
        return [];
      };

      const source = 'include "self.conf";';
      const result = await parse(source, {
        path: "root.conf",
        loader,
      });

      const cycleErrors = result.diagnostics.filter((d) => d.code === DiagnosticCode.IncludeCycle);
      expect(cycleErrors).toHaveLength(1);
    });

    it("should detect indirect cycle", async () => {
      const files: Record<string, string> = {
        "a.conf": 'include "b.conf";',
        "b.conf": 'include "a.conf";',
      };

      const loader: DocumentLoader = async (spec) => {
        const content = files[spec];
        if (!content) return [];
        return [{ source: content, resolvedPath: spec }];
      };

      const source = 'include "a.conf";';
      const result = await parse(source, {
        path: "root.conf",
        loader,
      });

      const cycleErrors = result.diagnostics.filter((d) => d.code === DiagnosticCode.IncludeCycle);
      expect(cycleErrors.length).toBeGreaterThan(0);
    });
  });

  describe("depth limiting", () => {
    it("should enforce max include depth", async () => {
      // Create a chain of includes
      const loader: DocumentLoader = async (spec) => {
        const depth = parseInt(spec.replace("level", "").replace(".conf", ""), 10);
        const nextLevel = depth + 1;
        return [
          {
            source: `include "level${nextLevel}.conf";`,
            resolvedPath: spec,
          },
        ];
      };

      const source = 'include "level0.conf";';
      const result = await parse(source, {
        path: "root.conf",
        loader,
        maxIncludeDepth: 3,
      });

      const depthErrors = result.diagnostics.filter((d) => d.code === DiagnosticCode.IncludeDepthExceeded);
      expect(depthErrors.length).toBeGreaterThan(0);
    });
  });

  describe("error handling", () => {
    it("should handle resolver failures", async () => {
      const loader: DocumentLoader = async () => {
        throw new Error("Network error");
      };

      const source = 'include "remote.conf";';
      const result = await parse(source, {
        path: "/root/root.conf",
        loader,
      });

      const resolverErrors = result.diagnostics.filter((d) => d.code === DiagnosticCode.IncludeResolverFailed);
      expect(resolverErrors).toHaveLength(1);
      expect(resolverErrors[0].message).toContain("Network error");
    });

    it("should require string literal for include path", async () => {
      const loader: DocumentLoader = async () => [];

      const source = "include some_var;";
      const result = await parse(source, {
        path: "/root/root.conf",
        loader,
      });

      const errors = result.diagnostics.filter((d) => d.code === DiagnosticCode.ExpectedStringLiteral);
      expect(errors).toHaveLength(1);
    });
  });

  describe("document graph", () => {
    it("should build correct graph structure", async () => {
      const files: Record<string, string> = {
        "shared.conf": "shared_setting 1;",
        "a.conf": 'include "shared.conf"; a_setting 2;',
        "b.conf": 'include "shared.conf"; b_setting 3;',
      };

      const loader: DocumentLoader = async (spec) => {
        const content = files[spec];
        if (!content) return [];
        return [{ source: content, resolvedPath: spec }];
      };

      const source = 'include "a.conf"; include "b.conf";';
      const result = await parse(source, {
        path: "root.conf",
        loader,
      });

      // Should have 4 nodes: root, a.conf, b.conf, shared.conf
      expect(result.nodes.size).toBe(4);

      // shared.conf should only be parsed once (cached)
      const sharedNode = result.nodes.get("shared.conf");
      expect(sharedNode).toBeDefined();
    });

    it("should preserve include order in edges", async () => {
      const loader: DocumentLoader = async (spec) => {
        return [{ source: `from_${spec};`, resolvedPath: spec }];
      };

      const source = 'include "first.conf"; include "second.conf";';
      const result = await parse(source, {
        path: "root.conf",
        loader,
      });

      const first = result.root.parseResult.cst.children[0]!;
      const second = result.root.parseResult.cst.children[1]!;
      expect(result.root.includes.get(first)!.spec).toBe("first.conf");
      expect(result.root.includes.get(second)!.spec).toBe("second.conf");
    });
  });
});
