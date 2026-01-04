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
  TokenType,
  DiagnosticCode,
  DiagnosticSeverity,
  isTrivia,
  isComment,
  isWhitespace,
  isTerminator,
  type IToken,
  type ISourceLocation,
  type ISourceSpan,
  type ILexResult,
  type IDiagnostic,
} from './tokens.js';

// Lexer
export { lex, Lexer } from './lexer.js';

// CST types and utilities
export {
  CstNodeKind,
  serializeCst,
  serializeRange,
  serializeDirective,
  getSpanForRange,
  getDirectiveName,
  getDirectiveArgs,
  createDocument,
  type ICstNode,
  type ICstDocument,
  type ICstDirective,
  type ITokenRange,
} from './cst.js';

// Parser
export { type IParseResult } from './parser.js';

// AST facade
export {
  createAst,
  walkDirectives,
  findDirectives,
  type IAstDocument,
  type IAstDirective,
  type IAstDirectiveList,
} from './ast.js';

// Document I/O + parsing
export {
  type ILoadContext,
  type ILoadedDocument,
  type DocumentLoader,
  type DocumentWriter,
  composeLoaders,
} from './io.js';

export {
  parse,
  type IParseConfig,
} from './parse.js';

export {
  type IDocumentEdge,
  type IDocumentNode,
  type IDocumentGraph,
} from './graph.js';

// Include-expanded traversal
export { iterateDirectives } from './iterate.js';

// Persistence
export { save } from './save.js';

// Delegator
export {
  DirectiveDelegator,
  walkScopeDocument,
  walkScopeBody,
  createChildDelegator,
  type DirectiveHandler,
  type IScopeResult,
  type IDelegatorHooks,
} from './delegator.js';
