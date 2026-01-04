/**
 * Async include resolution for config files.
 *
 * Key features:
 * - Document graph representation (not inlined)
 * - Async resolver interface (no I/O in core)
 * - Cycle detection and depth limiting
 * - Glob support with deterministic ordering
 */

import {
  DiagnosticCode,
  DiagnosticSeverity,
  TokenType,
  type IDiagnostic,
} from './tokens.js';
import { parseDocument, type IParseResult } from './parser.js';
import {
  getDirectiveName,
  getDirectiveArgs,
  type ICstDocument,
  type ICstDirective,
} from './cst.js';
import { createAst, type IAstDocument } from './ast.js';

/**
 * Include resolver context.
 */
export interface IIncludeContext {
  /** Path of the including file */
  parentPath: string;
  /** Current include depth */
  depth: number;
}

/**
 * Resolved include source.
 */
export interface IResolvedInclude {
  /** Source text content */
  source: string;
  /** Resolved path (used for cycle detection and graph edges) */
  resolvedPath: string;
}

/**
 * Include resolver function.
 * Returns array of resolved sources (for glob support).
 */
export type IncludeResolver = (
  spec: string,
  ctx: IIncludeContext
) => Promise<IResolvedInclude[]>;

/**
 * Edge in the document graph.
 */
export interface IDocumentEdge {
  /** The include directive that created this edge */
  directive: ICstDirective;
  /** The include spec (path or glob) */
  spec: string;
  /** Resolved target documents (multiple for globs) */
  targets: IDocumentNode[];
}

/**
 * Node in the document graph.
 */
export interface IDocumentNode {
  /** Resolved path (unique identifier) */
  resolvedPath: string;
  /** Parse result for this document */
  parseResult: IParseResult;
  /** AST facade */
  ast: IAstDocument;
  /** Outgoing include edges */
  includes: IDocumentEdge[];
}

/**
 * Document graph representing a set of included files.
 */
export interface IDocumentGraph {
  /** Root document node */
  root: IDocumentNode;
  /** All nodes by resolved path */
  nodes: Map<string, IDocumentNode>;
  /** All diagnostics across all documents */
  diagnostics: IDiagnostic[];
}

/**
 * Configuration for async parsing with includes.
 */
export interface IParseConfig {
  /**
   * Absolute or workspace-relative path for the root document.
   *
   * Used only for diagnostics and for include resolution context; no I/O is
   * performed by this package.
   */
  path?: string;
  /**
   * Include resolver function.
   *
   * Required. This package never performs I/O; you must provide a resolver,
   * even if it is a no-op.
   */
  includeResolver: IncludeResolver;
  /** Maximum include depth (default: 16) */
  maxIncludeDepth?: number;
}

const DEFAULT_MAX_DEPTH = 16;

/**
 * Parse a config file with async include resolution.
 */
export async function parse(source: string, config: IParseConfig): Promise<IDocumentGraph> {
  if (!config || typeof config.includeResolver !== 'function') {
    throw new Error('Malformed parser configuration: includeResolver is required');
  }

  const rootPath = config.path ?? '<root>';
  const resolver = config.includeResolver;
  const maxDepth = config?.maxIncludeDepth ?? DEFAULT_MAX_DEPTH;

  const diagnostics: IDiagnostic[] = [];
  const nodes = new Map<string, IDocumentNode>();
  const visiting = new Set<string>();

  async function processDocument(
    src: string,
    resolvedPath: string,
    depth: number
  ): Promise<IDocumentNode> {
    // Check for cycles
    if (visiting.has(resolvedPath)) {
      diagnostics.push({
        code: DiagnosticCode.IncludeCycle,
        severity: DiagnosticSeverity.Error,
        message: `Circular include detected: ${resolvedPath}`,
        span: { start: { offset: 0, line: 0, column: 0 }, end: { offset: 0, line: 0, column: 0 } },
        sourceId: resolvedPath,
      });
      // Return cached node if available
      const cached = nodes.get(resolvedPath);
      if (cached) return cached;
      // Create empty node for cycle
      const emptyResult = parseDocument('', { sourceId: resolvedPath });
      const node: IDocumentNode = {
        resolvedPath,
        parseResult: emptyResult,
        ast: createAst(emptyResult.cst),
        includes: [],
      };
      nodes.set(resolvedPath, node);
      return node;
    }

    // Check cache
    const cached = nodes.get(resolvedPath);
    if (cached) return cached;

    // Check depth
    if (depth > maxDepth) {
      diagnostics.push({
        code: DiagnosticCode.IncludeDepthExceeded,
        severity: DiagnosticSeverity.Error,
        message: `Include depth exceeded (max: ${maxDepth})`,
        span: { start: { offset: 0, line: 0, column: 0 }, end: { offset: 0, line: 0, column: 0 } },
        sourceId: resolvedPath,
      });
      const emptyResult = parseDocument('', { sourceId: resolvedPath });
      const node: IDocumentNode = {
        resolvedPath,
        parseResult: emptyResult,
        ast: createAst(emptyResult.cst),
        includes: [],
      };
      nodes.set(resolvedPath, node);
      return node;
    }

    visiting.add(resolvedPath);

    // Parse the document
    const parseResult = parseDocument(src, { sourceId: resolvedPath });
    diagnostics.push(...parseResult.errors, ...parseResult.warnings);

    const ast = createAst(parseResult.cst);
    const includes: IDocumentEdge[] = [];

    // Create node (before processing includes to handle self-references)
    const node: IDocumentNode = {
      resolvedPath,
      parseResult,
      ast,
      includes,
    };
    nodes.set(resolvedPath, node);

    // Process include directives
    const includeDirectives = findIncludeDirectives(parseResult.cst);

    for (const directive of includeDirectives) {
      const spec = getIncludeSpec(parseResult.cst, directive);
      if (!spec) {
        diagnostics.push({
          code: DiagnosticCode.ExpectedStringLiteral,
          severity: DiagnosticSeverity.Error,
          message: 'Include directive requires a string literal path',
          span: { start: { offset: 0, line: 0, column: 0 }, end: { offset: 0, line: 0, column: 0 } },
          sourceId: resolvedPath,
        });
        continue;
      }

      try {
        const resolved = await resolver(spec, {
          parentPath: resolvedPath,
          depth,
        });

        if (resolved.length === 0) {
          diagnostics.push({
            code: DiagnosticCode.IncludeNoMatches,
            severity: DiagnosticSeverity.Warning,
            message: `Include pattern matched no files: ${spec}`,
            span: { start: { offset: 0, line: 0, column: 0 }, end: { offset: 0, line: 0, column: 0 } },
            sourceId: resolvedPath,
          });
        }

        // Sort by resolved path for deterministic ordering
        resolved.sort((a, b) => a.resolvedPath.localeCompare(b.resolvedPath));

        const targets: IDocumentNode[] = [];
        for (const r of resolved) {
          const targetNode = await processDocument(r.source, r.resolvedPath, depth + 1);
          targets.push(targetNode);
        }

        includes.push({ directive, spec, targets });
      } catch (e) {
        const err = e as Error;
        diagnostics.push({
          code: DiagnosticCode.IncludeResolverFailed,
          severity: DiagnosticSeverity.Error,
          message: `Include resolver failed for '${spec}': ${err.message}`,
          span: { start: { offset: 0, line: 0, column: 0 }, end: { offset: 0, line: 0, column: 0 } },
          sourceId: resolvedPath,
        });
      }
    }

    visiting.delete(resolvedPath);
    return node;
  }

  const root = await processDocument(source, rootPath, 0);

  const graph: IDocumentGraph = { root, nodes, diagnostics };
  for (const node of nodes.values()) {
    node.parseResult.cst.graph = graph;
  }

  return graph;
}

/**
 * Find all include directives in a CST document.
 */
function findIncludeDirectives(cst: ICstDocument): ICstDirective[] {
  const result: ICstDirective[] = [];

  function visit(directives: ICstDirective[]): void {
    for (const d of directives) {
      if (getDirectiveName(cst, d) === 'include') {
        result.push(d);
      }
      if (d.body) {
        visit(d.body);
      }
    }
  }

  visit(cst.children);
  return result;
}

/**
 * Get the include spec (path) from an include directive.
 * Returns null if the directive doesn't have a valid string argument.
 */
function getIncludeSpec(cst: ICstDocument, directive: ICstDirective): string | null {
  const args = getDirectiveArgs(cst, directive);
  if (args.length === 0) return null;

  const firstArg = args[0];
  if (firstArg.type !== TokenType.String) return null;

  return String(firstArg.value);
}
