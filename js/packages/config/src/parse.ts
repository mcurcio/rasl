import { createAst } from "./ast.js";
import { getDirectiveArgs, getDirectiveName, type ICstDirective, type ICstDocument } from "./cst.js";
import type { IDocumentEdge, IDocumentGraph, IDocumentNode } from "./graph.js";
import { composeLoaders, type DocumentLoader, syntheticSpan } from "./io.js";
import { parseDocument } from "./parser.js";
import { DiagnosticCode, DiagnosticSeverity, type IDiagnostic, TokenType } from "./tokens.js";

/**
 * Configuration for parsing a root document into a document graph.
 */
export interface IParseConfig {
  /**
   * Optional root document identity (file path, URL, etc).
   *
   * Used only for include resolution context and diagnostics.
   */
  path?: string;
  /**
   * Document loader(s).
   *
   * Required. The core parser performs no I/O; you must provide at least one
   * loader, even if it is a no-op.
   */
  loader: DocumentLoader | readonly DocumentLoader[];
  /** Maximum include depth (default: 16). */
  maxIncludeDepth?: number;
}

const DEFAULT_MAX_DEPTH = 16;

/**
 * Parse a config source string into a document graph.
 *
 * Includes are resolved via the provided loader. Include ordering and nesting
 * are preserved in the directive tree; resolution results are indexed by the
 * originating include directive.
 */
export async function parse(source: string, config: IParseConfig): Promise<IDocumentGraph> {
  if (!config || !config.loader) {
    throw new Error("Malformed parser configuration: loader is required");
  }

  const rootPath = config.path ?? "<root>";
  const maxDepth = config.maxIncludeDepth ?? DEFAULT_MAX_DEPTH;
  const loader = typeof config.loader === "function" ? config.loader : composeLoaders(config.loader);

  const diagnostics: IDiagnostic[] = [];
  const nodes = new Map<string, IDocumentNode>();
  const visiting = new Set<string>();

  const includeDirectives = (cst: ICstDocument): ICstDirective[] => {
    const out: ICstDirective[] = [];

    const visit = (dirs: ICstDirective[]): void => {
      for (const d of dirs) {
        if (getDirectiveName(cst, d) === "include") out.push(d);
        if (d.body) visit(d.body);
      }
    };

    visit(cst.children);
    return out;
  };

  const includeSpec = (cst: ICstDocument, directive: ICstDirective): string | null => {
    const args = getDirectiveArgs(cst, directive);
    if (args.length === 0) return null;
    const first = args[0]!;
    if (first.type !== TokenType.String) return null;
    return String(first.value);
  };

  async function processDocument(src: string, resolvedPath: string, depth: number): Promise<IDocumentNode> {
    if (visiting.has(resolvedPath)) {
      diagnostics.push({
        code: DiagnosticCode.IncludeCycle,
        severity: DiagnosticSeverity.Error,
        message: `Circular include detected: ${resolvedPath}`,
        span: syntheticSpan(),
        sourceId: resolvedPath,
      });

      const cached = nodes.get(resolvedPath);
      if (cached) return cached;

      const emptyResult = parseDocument("", { sourceId: resolvedPath });
      const emptyCst = emptyResult.cst;
      const emptyNode: IDocumentNode = {
        resolvedPath,
        source: "",
        parseResult: emptyResult,
        cst: emptyCst,
        ast: createAst(emptyCst),
        includes: new Map(),
      };
      nodes.set(resolvedPath, emptyNode);
      return emptyNode;
    }

    const cached = nodes.get(resolvedPath);
    if (cached) return cached;

    if (depth > maxDepth) {
      diagnostics.push({
        code: DiagnosticCode.IncludeDepthExceeded,
        severity: DiagnosticSeverity.Error,
        message: `Include depth exceeded (max: ${maxDepth})`,
        span: syntheticSpan(),
        sourceId: resolvedPath,
      });

      const emptyResult = parseDocument("", { sourceId: resolvedPath });
      const emptyCst = emptyResult.cst;
      const emptyNode: IDocumentNode = {
        resolvedPath,
        source: "",
        parseResult: emptyResult,
        cst: emptyCst,
        ast: createAst(emptyCst),
        includes: new Map(),
      };
      nodes.set(resolvedPath, emptyNode);
      return emptyNode;
    }

    visiting.add(resolvedPath);

    const parseResult = parseDocument(src, { sourceId: resolvedPath });
    diagnostics.push(...parseResult.errors, ...parseResult.warnings);

    const cst = parseResult.cst;
    const ast = createAst(cst);
    const includes = new Map<ICstDirective, IDocumentEdge>();

    const node: IDocumentNode = {
      resolvedPath,
      source: src,
      parseResult,
      cst,
      ast,
      includes,
    };
    nodes.set(resolvedPath, node);

    for (const directive of includeDirectives(cst)) {
      const spec = includeSpec(cst, directive);
      if (!spec) {
        diagnostics.push({
          code: DiagnosticCode.ExpectedStringLiteral,
          severity: DiagnosticSeverity.Error,
          message: "Include directive requires a string literal path",
          span: syntheticSpan(),
          sourceId: resolvedPath,
        });
        continue;
      }

      try {
        const resolved = await loader(spec, { parentPath: resolvedPath, depth });
        if (resolved.length === 0) {
          diagnostics.push({
            code: DiagnosticCode.IncludeNotFound,
            severity: DiagnosticSeverity.Error,
            message: `Include not found: ${spec}`,
            span: syntheticSpan(),
            sourceId: resolvedPath,
          });
          includes.set(directive, { directive, spec, targets: [] });
          continue;
        }

        resolved.sort((a, b) => a.resolvedPath.localeCompare(b.resolvedPath));

        const targets: IDocumentNode[] = [];
        for (const r of resolved) {
          targets.push(await processDocument(r.source, r.resolvedPath, depth + 1));
        }

        includes.set(directive, { directive, spec, targets });
      } catch (e) {
        diagnostics.push({
          code: DiagnosticCode.IncludeResolverFailed,
          severity: DiagnosticSeverity.Error,
          message: `Include resolver failed for '${spec}': ${(e as Error).message}`,
          span: syntheticSpan(),
          sourceId: resolvedPath,
        });
        includes.set(directive, { directive, spec, targets: [] });
      }
    }

    visiting.delete(resolvedPath);
    return node;
  }

  const root = await processDocument(source, rootPath, 0);
  return { root, nodes, diagnostics };
}
