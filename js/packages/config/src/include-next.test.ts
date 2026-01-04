/**
 * Tests for async include resolution.
 */

import { describe, it, expect } from 'vitest';
import { parseAsync, type IncludeResolver } from './include-next.js';
import { DiagnosticCode } from './tokens-next.js';

describe('Include Resolution', () => {
  describe('basic includes', () => {
    it('should parse without resolver (includes not expanded)', async () => {
      const source = 'include "other.conf";';
      const result = await parseAsync(source);
      expect(result.root.parseResult.errors).toHaveLength(0);
      expect(result.root.includes).toHaveLength(0); // No resolver provided
    });

    it('should resolve single include', async () => {
      const files: Record<string, string> = {
        'other.conf': 'listen 8080;',
      };

      const resolver: IncludeResolver = async (spec) => {
        const content = files[spec];
        if (!content) return [];
        return [{ source: content, resolvedPath: spec }];
      };

      const source = 'include "other.conf";';
      const result = await parseAsync(source, {
        basePath: '/root',
        includeResolver: resolver,
      });

      expect(result.root.includes).toHaveLength(1);
      expect(result.root.includes[0].targets).toHaveLength(1);
      expect(result.root.includes[0].targets[0].ast.children.length).toBe(1);
    });

    it('should resolve nested includes', async () => {
      const files: Record<string, string> = {
        'a.conf': 'include "b.conf";',
        'b.conf': 'listen 8080;',
      };

      const resolver: IncludeResolver = async (spec) => {
        const content = files[spec];
        if (!content) return [];
        return [{ source: content, resolvedPath: spec }];
      };

      const source = 'include "a.conf";';
      const result = await parseAsync(source, {
        basePath: '/root',
        includeResolver: resolver,
      });

      expect(result.nodes.size).toBe(3); // root + a.conf + b.conf
    });
  });

  describe('glob support', () => {
    it('should resolve multiple files from glob', async () => {
      const resolver: IncludeResolver = async (spec) => {
        if (spec === '*.conf') {
          return [
            { source: 'a 1;', resolvedPath: 'a.conf' },
            { source: 'b 2;', resolvedPath: 'b.conf' },
            { source: 'c 3;', resolvedPath: 'c.conf' },
          ];
        }
        return [];
      };

      const source = 'include "*.conf";';
      const result = await parseAsync(source, {
        includeResolver: resolver,
      });

      expect(result.root.includes).toHaveLength(1);
      expect(result.root.includes[0].targets).toHaveLength(3);
    });

    it('should sort glob matches by resolved path', async () => {
      const resolver: IncludeResolver = async (spec) => {
        if (spec === '*.conf') {
          // Return in non-sorted order
          return [
            { source: 'c 3;', resolvedPath: 'c.conf' },
            { source: 'a 1;', resolvedPath: 'a.conf' },
            { source: 'b 2;', resolvedPath: 'b.conf' },
          ];
        }
        return [];
      };

      const source = 'include "*.conf";';
      const result = await parseAsync(source, {
        includeResolver: resolver,
      });

      const paths = result.root.includes[0].targets.map((t) => t.resolvedPath);
      expect(paths).toEqual(['a.conf', 'b.conf', 'c.conf']);
    });

    it('should warn on no glob matches', async () => {
      const resolver: IncludeResolver = async () => [];

      const source = 'include "*.conf";';
      const result = await parseAsync(source, {
        includeResolver: resolver,
      });

      const warnings = result.diagnostics.filter(
        (d) => d.code === DiagnosticCode.IncludeNoMatches
      );
      expect(warnings).toHaveLength(1);
    });
  });

  describe('cycle detection', () => {
    it('should detect direct cycle', async () => {
      const resolver: IncludeResolver = async (spec) => {
        if (spec === 'self.conf') {
          return [{ source: 'include "self.conf";', resolvedPath: 'self.conf' }];
        }
        return [];
      };

      const source = 'include "self.conf";';
      const result = await parseAsync(source, {
        sourceId: 'root.conf',
        includeResolver: resolver,
      });

      const cycleErrors = result.diagnostics.filter(
        (d) => d.code === DiagnosticCode.IncludeCycle
      );
      expect(cycleErrors).toHaveLength(1);
    });

    it('should detect indirect cycle', async () => {
      const files: Record<string, string> = {
        'a.conf': 'include "b.conf";',
        'b.conf': 'include "a.conf";',
      };

      const resolver: IncludeResolver = async (spec) => {
        const content = files[spec];
        if (!content) return [];
        return [{ source: content, resolvedPath: spec }];
      };

      const source = 'include "a.conf";';
      const result = await parseAsync(source, {
        sourceId: 'root.conf',
        includeResolver: resolver,
      });

      const cycleErrors = result.diagnostics.filter(
        (d) => d.code === DiagnosticCode.IncludeCycle
      );
      expect(cycleErrors.length).toBeGreaterThan(0);
    });
  });

  describe('depth limiting', () => {
    it('should enforce max include depth', async () => {
      // Create a chain of includes
      const resolver: IncludeResolver = async (spec) => {
        const depth = parseInt(spec.replace('level', '').replace('.conf', ''), 10);
        const nextLevel = depth + 1;
        return [{
          source: `include "level${nextLevel}.conf";`,
          resolvedPath: spec,
        }];
      };

      const source = 'include "level0.conf";';
      const result = await parseAsync(source, {
        sourceId: 'root.conf',
        includeResolver: resolver,
        maxIncludeDepth: 3,
      });

      const depthErrors = result.diagnostics.filter(
        (d) => d.code === DiagnosticCode.IncludeDepthExceeded
      );
      expect(depthErrors.length).toBeGreaterThan(0);
    });
  });

  describe('error handling', () => {
    it('should handle resolver failures', async () => {
      const resolver: IncludeResolver = async () => {
        throw new Error('Network error');
      };

      const source = 'include "remote.conf";';
      const result = await parseAsync(source, {
        includeResolver: resolver,
      });

      const resolverErrors = result.diagnostics.filter(
        (d) => d.code === DiagnosticCode.IncludeResolverFailed
      );
      expect(resolverErrors).toHaveLength(1);
      expect(resolverErrors[0].message).toContain('Network error');
    });

    it('should require string literal for include path', async () => {
      const resolver: IncludeResolver = async () => [];

      const source = 'include some_var;';
      const result = await parseAsync(source, {
        includeResolver: resolver,
      });

      const errors = result.diagnostics.filter(
        (d) => d.code === DiagnosticCode.ExpectedStringLiteral
      );
      expect(errors).toHaveLength(1);
    });
  });

  describe('document graph', () => {
    it('should build correct graph structure', async () => {
      const files: Record<string, string> = {
        'shared.conf': 'shared_setting 1;',
        'a.conf': 'include "shared.conf"; a_setting 2;',
        'b.conf': 'include "shared.conf"; b_setting 3;',
      };

      const resolver: IncludeResolver = async (spec) => {
        const content = files[spec];
        if (!content) return [];
        return [{ source: content, resolvedPath: spec }];
      };

      const source = 'include "a.conf"; include "b.conf";';
      const result = await parseAsync(source, {
        sourceId: 'root.conf',
        includeResolver: resolver,
      });

      // Should have 4 nodes: root, a.conf, b.conf, shared.conf
      expect(result.nodes.size).toBe(4);

      // shared.conf should only be parsed once (cached)
      const sharedNode = result.nodes.get('shared.conf');
      expect(sharedNode).toBeDefined();
    });

    it('should preserve include order in edges', async () => {
      const resolver: IncludeResolver = async (spec) => {
        return [{ source: `from_${spec};`, resolvedPath: spec }];
      };

      const source = 'include "first.conf"; include "second.conf";';
      const result = await parseAsync(source, {
        includeResolver: resolver,
      });

      expect(result.root.includes).toHaveLength(2);
      expect(result.root.includes[0].spec).toBe('first.conf');
      expect(result.root.includes[1].spec).toBe('second.conf');
    });
  });
});
