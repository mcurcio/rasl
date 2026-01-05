/**
 * Tests for the config parser.
 */

import { describe, expect, it } from "vitest";

import { createAst } from "./ast.js";
import { getDirectiveArgs, getDirectiveName, serializeCst } from "./cst.js";
import { type DocumentLoader, parse } from "./index.js";

describe("Parser", () => {
  const loader: DocumentLoader = async () => [];

  describe("basic parsing", () => {
    it("should parse empty input", async () => {
      const graph = await parse("", { path: "root.conf", loader });
      expect(graph.root.parseResult.errors).toHaveLength(0);
      expect(graph.root.parseResult.cst.children).toHaveLength(0);
    });

    it("should parse simple directive with semicolon", async () => {
      const graph = await parse("listen 8080;", { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(1);
      expect(getDirectiveName(result.cst, result.cst.children[0])).toBe("listen");
      const args = getDirectiveArgs(result.cst, result.cst.children[0]);
      expect(args).toHaveLength(1);
      expect(args[0].value).toBe(8080);
    });

    it("should parse directive terminated by newline", async () => {
      const graph = await parse("listen 8080\n", { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(1);
    });

    it("should parse multiple directives on separate lines", async () => {
      const graph = await parse("listen 8080\nserver_name example.com\n", { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(2);
    });

    it("should parse multiple directives on one line with semicolons", async () => {
      const graph = await parse("listen 8080; server_name example.com;", { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(2);
    });

    it("should parse directive with block", async () => {
      const graph = await parse("server { listen 8080; }", { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(1);
      const server = result.cst.children[0];
      expect(getDirectiveName(result.cst, server)).toBe("server");
      expect(server.body).toHaveLength(1);
    });

    it("should parse nested blocks", async () => {
      const source = `
server {
  location / {
    root /var/www;
  }
}
`;
      const graph = await parse(source, { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(result.errors).toHaveLength(0);
      const server = result.cst.children[0];
      expect(server.body).toHaveLength(1);
      const location = server.body![0];
      expect(getDirectiveName(result.cst, location)).toBe("location");
      expect(location.body).toHaveLength(1);
    });
  });

  describe("argument parsing", () => {
    it("should parse string arguments", async () => {
      const graph = await parse('server_name "example.com";', { path: "root.conf", loader });
      const result = graph.root.parseResult;
      const args = getDirectiveArgs(result.cst, result.cst.children[0]);
      expect(args).toHaveLength(1);
      expect(args[0].value).toBe("example.com");
    });

    it("should parse multiple arguments", async () => {
      const graph = await parse("proxy_pass upstream 8080 true;", { path: "root.conf", loader });
      const result = graph.root.parseResult;
      const args = getDirectiveArgs(result.cst, result.cst.children[0]);
      expect(args).toHaveLength(3);
      expect(args[0].value).toBe("upstream");
      expect(args[1].value).toBe(8080);
      expect(args[2].value).toBe(true);
    });

    it("should parse bracket expressions", async () => {
      const graph = await parse("connect source[0:3] dest[0:3];", { path: "root.conf", loader });
      const result = graph.root.parseResult;
      const args = getDirectiveArgs(result.cst, result.cst.children[0]);
      expect(args.length).toBeGreaterThan(0);
    });

    it("should allow multi-line bracket lists", async () => {
      const source = `items [
  first,
  second,
  third
];`;
      const graph = await parse(source, { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(1);
    });
  });

  describe("round-trip serialization", () => {
    it("should round-trip simple directive", async () => {
      const source = "listen 8080;";
      const graph = await parse(source, { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(serializeCst(result.cst)).toBe(source);
    });

    it("should round-trip with whitespace", async () => {
      const source = "  listen   8080  ;  ";
      const graph = await parse(source, { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(serializeCst(result.cst)).toBe(source);
    });

    it("should round-trip with comments", async () => {
      const source = `// header comment
server {
  listen 8080; // inline comment
  /* block
     comment */
}
`;
      const graph = await parse(source, { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(serializeCst(result.cst)).toBe(source);
    });

    it("should round-trip complex config", async () => {
      const source = `
server {
  listen 8080;
  server_name "example.com";

  location / {
    root /var/www;
    index index.html;
  }

  // upstream config
  upstream backend {
    server 127.0.0.1:3000;
  }
}
`;
      const graph = await parse(source, { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(serializeCst(result.cst)).toBe(source);
    });

    it("should round-trip strings with escapes", async () => {
      const source = 'message "hello\\nworld";';
      const graph = await parse(source, { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(serializeCst(result.cst)).toBe(source);
    });
  });

  describe("AST facade", () => {
    it("should provide convenient directive access", async () => {
      const graph = await parse("server { listen 8080; }", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);
      expect(ast.children.length).toBe(1);
      const server = ast.children.at(0)!;
      expect(server.name).toBe("server");
      expect(server.body).not.toBeNull();
      expect(server.body!.length).toBe(1);
    });

    it("should provide argValues convenience accessor", async () => {
      const graph = await parse("proxy_pass upstream 8080 true;", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);
      const directive = ast.children.at(0)!;
      expect(directive.argValues).toEqual(["upstream", 8080, true]);
    });

    it("should support iteration", async () => {
      const graph = await parse("a 1; b 2; c 3;", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);
      const names: string[] = [];
      for (const d of ast.children) {
        names.push(d.name);
      }
      expect(names).toEqual(["a", "b", "c"]);
    });

    it("should support findByName", async () => {
      const graph = await parse("a 1; b 2; c 3;", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);
      const b = ast.children.findByName("b");
      expect(b).toBeDefined();
      expect(b!.argValues).toEqual([2]);
    });

    it("should support filterByName", async () => {
      const graph = await parse("a 1; b 2; a 3;", { path: "root.conf", loader });
      const ast = createAst(graph.root.parseResult.cst);
      const aDirectives = ast.children.filterByName("a");
      expect(aDirectives).toHaveLength(2);
    });
  });

  describe("error handling", () => {
    it("should report missing closing brace", async () => {
      const graph = await parse("server { listen 8080;", { path: "root.conf", loader });
      expect(graph.root.parseResult.errors.length).toBeGreaterThan(0);
    });

    it("should recover from errors and continue parsing", async () => {
      const graph = await parse("server { } valid 123;", { path: "root.conf", loader });
      expect(graph.root.parseResult.cst.children.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe("nginx-style compatibility", () => {
    it("should parse typical nginx server block", async () => {
      const source = `
server {
  listen 80;
  listen 443 ssl;
  server_name example.com www.example.com;

  location / {
    proxy_pass http://backend;
  }
}
`;
      const graph = await parse(source, { path: "root.conf", loader });
      const result = graph.root.parseResult;
      expect(result.errors).toHaveLength(0);
      expect(serializeCst(result.cst)).toBe(source);
    });
  });
});
