/**
 * Tests for the config parser.
 */

import { describe, it, expect } from 'vitest';
import { parse } from './parser.js';
import { serializeCst, getDirectiveName, getDirectiveArgs } from './cst.js';
import { createAst } from './ast.js';

describe('Parser', () => {
  describe('basic parsing', () => {
    it('should parse empty input', () => {
      const result = parse('');
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(0);
    });

    it('should parse simple directive with semicolon', () => {
      const result = parse('listen 8080;');
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(1);
      expect(getDirectiveName(result.cst, result.cst.children[0])).toBe('listen');
      const args = getDirectiveArgs(result.cst, result.cst.children[0]);
      expect(args).toHaveLength(1);
      expect(args[0].value).toBe(8080);
    });

    it('should parse directive terminated by newline', () => {
      const result = parse('listen 8080\n');
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(1);
    });

    it('should parse multiple directives on separate lines', () => {
      const result = parse('listen 8080\nserver_name example.com\n');
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(2);
    });

    it('should parse multiple directives on one line with semicolons', () => {
      const result = parse('listen 8080; server_name example.com;');
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(2);
    });

    it('should parse directive with block', () => {
      const result = parse('server { listen 8080; }');
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(1);
      const server = result.cst.children[0];
      expect(getDirectiveName(result.cst, server)).toBe('server');
      expect(server.body).toHaveLength(1);
    });

    it('should parse nested blocks', () => {
      const source = `
server {
  location / {
    root /var/www;
  }
}
`;
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
      const server = result.cst.children[0];
      expect(server.body).toHaveLength(1);
      const location = server.body![0];
      expect(getDirectiveName(result.cst, location)).toBe('location');
      expect(location.body).toHaveLength(1);
    });
  });

  describe('argument parsing', () => {
    it('should parse string arguments', () => {
      const result = parse('server_name "example.com";');
      const args = getDirectiveArgs(result.cst, result.cst.children[0]);
      expect(args).toHaveLength(1);
      expect(args[0].value).toBe('example.com');
    });

    it('should parse multiple arguments', () => {
      const result = parse('proxy_pass upstream 8080 true;');
      const args = getDirectiveArgs(result.cst, result.cst.children[0]);
      expect(args).toHaveLength(3);
      expect(args[0].value).toBe('upstream');
      expect(args[1].value).toBe(8080);
      expect(args[2].value).toBe(true);
    });

    it('should parse bracket expressions', () => {
      const result = parse('connect source[0:3] dest[0:3];');
      const args = getDirectiveArgs(result.cst, result.cst.children[0]);
      expect(args.length).toBeGreaterThan(0);
    });

    it('should allow multi-line bracket lists', () => {
      const source = `items [
  first,
  second,
  third
];`;
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
      expect(result.cst.children).toHaveLength(1);
    });
  });

  describe('round-trip serialization', () => {
    it('should round-trip simple directive', () => {
      const source = 'listen 8080;';
      const result = parse(source);
      expect(serializeCst(result.cst)).toBe(source);
    });

    it('should round-trip with whitespace', () => {
      const source = '  listen   8080  ;  ';
      const result = parse(source);
      expect(serializeCst(result.cst)).toBe(source);
    });

    it('should round-trip with comments', () => {
      const source = `// header comment
server {
  listen 8080; // inline comment
  /* block
     comment */
}
`;
      const result = parse(source);
      expect(serializeCst(result.cst)).toBe(source);
    });

    it('should round-trip complex config', () => {
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
      const result = parse(source);
      expect(serializeCst(result.cst)).toBe(source);
    });

    it('should round-trip strings with escapes', () => {
      const source = 'message "hello\\nworld";';
      const result = parse(source);
      expect(serializeCst(result.cst)).toBe(source);
    });
  });

  describe('AST facade', () => {
    it('should provide convenient directive access', () => {
      const result = parse('server { listen 8080; }');
      const ast = createAst(result.cst);
      expect(ast.children.length).toBe(1);
      const server = ast.children.at(0)!;
      expect(server.name).toBe('server');
      expect(server.body).not.toBeNull();
      expect(server.body!.length).toBe(1);
    });

    it('should provide argValues convenience accessor', () => {
      const result = parse('proxy_pass upstream 8080 true;');
      const ast = createAst(result.cst);
      const directive = ast.children.at(0)!;
      expect(directive.argValues).toEqual(['upstream', 8080, true]);
    });

    it('should support iteration', () => {
      const result = parse('a 1; b 2; c 3;');
      const ast = createAst(result.cst);
      const names: string[] = [];
      for (const d of ast.children) {
        names.push(d.name);
      }
      expect(names).toEqual(['a', 'b', 'c']);
    });

    it('should support findByName', () => {
      const result = parse('a 1; b 2; c 3;');
      const ast = createAst(result.cst);
      const b = ast.children.findByName('b');
      expect(b).toBeDefined();
      expect(b!.argValues).toEqual([2]);
    });

    it('should support filterByName', () => {
      const result = parse('a 1; b 2; a 3;');
      const ast = createAst(result.cst);
      const aDirectives = ast.children.filterByName('a');
      expect(aDirectives).toHaveLength(2);
    });
  });

  describe('error handling', () => {
    it('should report missing closing brace', () => {
      const result = parse('server { listen 8080;');
      expect(result.errors.length).toBeGreaterThan(0);
    });

    it('should recover from errors and continue parsing', () => {
      const result = parse('server { } valid 123;');
      expect(result.cst.children.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('nginx-style compatibility', () => {
    it('should parse typical nginx server block', () => {
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
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
      expect(serializeCst(result.cst)).toBe(source);
    });
  });
});
