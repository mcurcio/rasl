/**
 * @rasl/config - Generic nginx-style configuration parsing toolkit
 *
 * A domain-agnostic parsing library for nginx-style config files with:
 * - Byte-identical round-tripping via full-fidelity CST
 * - Structured diagnostics with stable codes
 * - Async include resolution with document graph
 * - Strongly-typed directive delegation
 */

// Token types and utilities
export {
  DiagnosticCode,
  DiagnosticSeverity,
  type IDiagnostic,
  type ILexResult,
  isComment,
  type ISourceLocation,
  type ISourceSpan,
  isTerminator,
  isTrivia,
  isWhitespace,
  type IToken,
  TokenType,
} from "./tokens.js";

// Lexer
export { lex, Lexer } from "./lexer.js";

// CST types and utilities
export {
  createDocument,
  CstNodeKind,
  getDirectiveArgs,
  getDirectiveName,
  getSpanForRange,
  type ICstDirective,
  type ICstDocument,
  type ICstNode,
  type ITokenRange,
  serializeCst,
  serializeDirective,
  serializeRange,
} from "./cst.js";

// Parser
export { type IParseResult } from "./parser.js";

// AST facade
export {
  createAst,
  findDirectives,
  type IAstDirective,
  type IAstDirectiveList,
  type IAstDocument,
  walkDirectives,
} from "./ast.js";

// Document I/O + parsing
export { type IDocumentEdge, type IDocumentGraph, type IDocumentNode } from "./graph.js";
export {
  composeLoaders,
  type DocumentLoader,
  type DocumentWriter,
  type ILoadContext,
  type ILoadedDocument,
} from "./io.js";
export { type IParseConfig, parse } from "./parse.js";

// Include-expanded traversal
export { iterateDirectives } from "./iterate.js";

// Persistence
export { save } from "./save.js";

// Delegator
export {
  createChildDelegator,
  DirectiveDelegator,
  type DirectiveHandler,
  type IDelegatorHooks,
  type IScopeResult,
  walkScopeBody,
  walkScopeDocument,
} from "./delegator.js";
