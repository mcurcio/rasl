/**
 * Tests for the directive delegator.
 */

import { describe, expect, it, vi } from "vitest";

import { createAst } from "./ast.js";
import { createChildDelegator, DirectiveDelegator, walkScopeDocument } from "./delegator.js";
import { type DocumentLoader, parse } from "./index.js";

describe("DirectiveDelegator", () => {
  const loader: DocumentLoader = async () => [];

  describe("basic dispatch", () => {
    it("should dispatch to registered handler", async () => {
      const handler = vi.fn();
      const delegator = new DirectiveDelegator<void>();
      delegator.register("listen", handler);

      const graph = await parse("listen 8080;", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);

      walkScopeDocument(ast, delegator, undefined);

      expect(handler).toHaveBeenCalledTimes(1);
      expect(handler.mock.calls[0][0].name).toBe("listen");
    });

    it("should pass context to handler", async () => {
      interface Ctx {
        port?: number;
      }
      const handler = vi.fn((directive, ctx: Ctx) => {
        ctx.port = directive.argValues[0] as number;
      });

      const delegator = new DirectiveDelegator<Ctx>();
      delegator.register("listen", handler);

      const graph = await parse("listen 8080;", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);
      const ctx: Ctx = {};

      walkScopeDocument(ast, delegator, ctx);

      expect(ctx.port).toBe(8080);
    });

    it("should call onUnknownDirective for unregistered names", async () => {
      const unknownHandler = vi.fn();
      const delegator = new DirectiveDelegator<void>({
        hooks: { onUnknownDirective: unknownHandler },
      });

      const graph = await parse("unknown_directive 123;", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);

      walkScopeDocument(ast, delegator, undefined);

      expect(unknownHandler).toHaveBeenCalledTimes(1);
      expect(unknownHandler.mock.calls[0][0].name).toBe("unknown_directive");
    });
  });

  describe("scope handling", () => {
    it("should process block body with returned scope", async () => {
      const serverHandler = vi.fn();
      const listenHandler = vi.fn();

      const serverScope = new DirectiveDelegator<void>();
      serverScope.register("listen", listenHandler);

      const rootScope = new DirectiveDelegator<void>();
      rootScope.register("server", (directive) => {
        serverHandler(directive);
        return { scope: serverScope, ctx: undefined };
      });

      const graph = await parse("server { listen 8080; }", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);

      walkScopeDocument(ast, rootScope, undefined);

      expect(serverHandler).toHaveBeenCalledTimes(1);
      expect(listenHandler).toHaveBeenCalledTimes(1);
    });

    it("should support nested scopes", async () => {
      const calls: string[] = [];

      const locationScope = new DirectiveDelegator<void>();
      locationScope.register("root", () => {
        calls.push("root");
      });

      const serverScope = new DirectiveDelegator<void>();
      serverScope.register("listen", () => {
        calls.push("listen");
      });
      serverScope.register("location", () => {
        calls.push("location");
        return { scope: locationScope, ctx: undefined };
      });

      const rootScope = new DirectiveDelegator<void>();
      rootScope.register("server", () => {
        calls.push("server");
        return { scope: serverScope, ctx: undefined };
      });

      const source = `
	server {
	  listen 8080;
	  location / {
	    root /var/www;
	  }
	}
	`;
      const graph = await parse(source, { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);

      walkScopeDocument(ast, rootScope, undefined);

      expect(calls).toEqual(["server", "listen", "location", "root"]);
    });
  });

  describe("lifecycle hooks", () => {
    it("should call onEnterScope and onExitScope", async () => {
      const enterSpy = vi.fn();
      const exitSpy = vi.fn();

      const delegator = new DirectiveDelegator<void>({
        hooks: {
          onEnterScope: enterSpy,
          onExitScope: exitSpy,
        },
      });

      const graph = await parse("a 1;", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);

      walkScopeDocument(ast, delegator, undefined);

      expect(enterSpy).toHaveBeenCalledTimes(1);
      expect(exitSpy).toHaveBeenCalledTimes(1);
      // Document scope has null owner
      expect(enterSpy.mock.calls[0][0]).toBeNull();
    });

    it("should call onBeforeDirective and onAfterDirective", async () => {
      const beforeSpy = vi.fn();
      const afterSpy = vi.fn();

      const delegator = new DirectiveDelegator<void>({
        hooks: {
          onBeforeDirective: beforeSpy,
          onAfterDirective: afterSpy,
        },
      });
      delegator.register("a", () => {});

      const graph = await parse("a 1; a 2;", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);

      walkScopeDocument(ast, delegator, undefined);

      expect(beforeSpy).toHaveBeenCalledTimes(2);
      expect(afterSpy).toHaveBeenCalledTimes(2);
    });
  });

  describe("parent delegation", () => {
    it("should inherit handlers from parent", async () => {
      const parentHandler = vi.fn();
      const childHandler = vi.fn();

      const parent = new DirectiveDelegator<void>();
      parent.register("inherited", parentHandler);

      const child = createChildDelegator(parent);
      child.register("local", childHandler);

      const graph = await parse("inherited 1; local 2;", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);

      walkScopeDocument(ast, child, undefined);

      expect(parentHandler).toHaveBeenCalledTimes(1);
      expect(childHandler).toHaveBeenCalledTimes(1);
    });

    it("should override parent handlers", async () => {
      const parentHandler = vi.fn();
      const childHandler = vi.fn();

      const parent = new DirectiveDelegator<void>();
      parent.register("override", parentHandler);

      const child = createChildDelegator(parent);
      child.register("override", childHandler);

      const graph = await parse("override 1;", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);

      walkScopeDocument(ast, child, undefined);

      expect(parentHandler).not.toHaveBeenCalled();
      expect(childHandler).toHaveBeenCalledTimes(1);
    });

    it("should list all legal directives including inherited", () => {
      const parent = new DirectiveDelegator<void>();
      parent.register("parent_dir", () => {});

      const child = createChildDelegator(parent);
      child.register("child_dir", () => {});

      const legal = child.legalDirectives();
      expect(legal).toContain("parent_dir");
      expect(legal).toContain("child_dir");
    });
  });

  describe("context transformation", () => {
    it("should support different context types for child scopes", async () => {
      interface RootCtx {
        servers: string[];
      }
      interface ServerCtx {
        name: string;
        ports: number[];
      }

      const rootScope = new DirectiveDelegator<RootCtx>();
      const serverScope = new DirectiveDelegator<ServerCtx>();

      serverScope.register("listen", (directive, ctx) => {
        ctx.ports.push(directive.argValues[0] as number);
      });

      rootScope.register("server", (directive, ctx) => {
        const serverName = directive.argValues[0] as string;
        ctx.servers.push(serverName);
        return {
          scope: serverScope,
          ctx: { name: serverName, ports: [] },
        };
      });

      const source = `
	server backend {
	  listen 8080;
	  listen 8081;
	}
	server frontend {
	  listen 80;
	}
	`;
      const graph = await parse(source, { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);
      const ctx: RootCtx = { servers: [] };

      walkScopeDocument(ast, rootScope, ctx);

      expect(ctx.servers).toEqual(["backend", "frontend"]);
    });
  });

  describe("handles method", () => {
    it("should return true for registered handlers", () => {
      const delegator = new DirectiveDelegator<void>();
      delegator.register("known", () => {});

      expect(delegator.handles("known")).toBe(true);
      expect(delegator.handles("unknown")).toBe(false);
    });

    it("should check parent chain", () => {
      const parent = new DirectiveDelegator<void>();
      parent.register("parent_handler", () => {});

      const child = createChildDelegator(parent);

      expect(child.handles("parent_handler")).toBe(true);
    });
  });
});
