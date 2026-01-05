import type { IAstDocument } from "./ast.js";
import type { ICstDirective, ICstDocument } from "./cst.js";
import type { IParseResult } from "./parser.js";
import type { IDiagnostic } from "./tokens.js";

/**
 * Edge in the document graph.
 *
 * Edges are created by `include` directives which live inside the CST/AST
 * directive tree. Resolution details are stored here and keyed by the
 * originating directive node (via `DocumentNode.includes`).
 */
export interface IDocumentEdge {
  /** The include directive that created this edge (in the parent document). */
  directive: ICstDirective;
  /** The include spec (path or glob). */
  spec: string;
  /** Resolved target documents (multiple for globs). */
  targets: IDocumentNode[];
}

/**
 * Node in the document graph.
 *
 * Represents a single persisted document (file, URL, etc).
 */
export interface IDocumentNode {
  /** Resolved path (unique identifier; semantics are loader-defined). */
  resolvedPath: string;
  /** Original source text as loaded. */
  source: string;
  /** Parse result for this document. */
  parseResult: IParseResult;
  /** CST for this document (full-fidelity). */
  cst: ICstDocument;
  /** AST facade for this document. */
  ast: IAstDocument;
  /**
   * Include resolution results keyed by the include directive node.
   *
   * This preserves ordering and nesting via the normal directive tree, while
   * still allowing quick access to resolved targets when walking directives.
   */
  includes: Map<ICstDirective, IDocumentEdge>;
}

/**
 * Document graph representing the root document plus all resolved includes.
 *
 * Even if there are no includes, this is still a one-node graph.
 */
export interface IDocumentGraph {
  /** Root document node. */
  root: IDocumentNode;
  /** All nodes by resolved path. */
  nodes: Map<string, IDocumentNode>;
  /** All diagnostics across all documents. */
  diagnostics: IDiagnostic[];
}
