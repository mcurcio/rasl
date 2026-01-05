/**
 * Concrete Syntax Tree types for config files.
 *
 * Key design:
 * - CST document owns the full token stream
 * - Directive nodes reference token ranges (not copies)
 * - Serialization is token concatenation for byte-identical round-tripping
 */

import type { ISourceSpan, IToken } from "./tokens.js";

/**
 * CST node kinds.
 */
export const CstNodeKind = {
  Document: "document",
  Directive: "directive",
} as const;
export type CstNodeKind = (typeof CstNodeKind)[keyof typeof CstNodeKind];

/**
 * Token range reference (start/end indices into document's token array).
 */
export interface ITokenRange {
  /** Start index (inclusive) */
  start: number;
  /** End index (exclusive) */
  end: number;
}

/**
 * Base interface for all CST nodes.
 */
export interface ICstNode {
  kind: CstNodeKind;
  /** Token range covering this entire node */
  tokenRange: ITokenRange;
}

/**
 * Root document node.
 * Owns the full token stream for round-tripping.
 */
export interface ICstDocument extends ICstNode {
  kind: typeof CstNodeKind.Document;
  /** Full token stream including all trivia */
  tokens: IToken[];
  /** Top-level directives */
  children: ICstDirective[];
  /** Source text (for verification) */
  source: string;
  /** Optional source identifier */
  sourceId?: string;
}

/**
 * A directive node.
 *
 * In nginx-style syntax, both statements and blocks are directives:
 * - Statement: `name arg1 arg2;` or `name arg1 arg2\n`
 * - Block: `name arg1 { ... }`
 */
export interface ICstDirective extends ICstNode {
  kind: typeof CstNodeKind.Directive;
  /** Token range for the directive name */
  nameRange: ITokenRange;
  /** Token ranges for each argument (non-trivia tokens between name and body/terminator) */
  argRanges: ITokenRange[];
  /** Child directives if this is a block, null otherwise */
  body: ICstDirective[] | null;
  /** Token range for the body (including braces), null if no body */
  bodyRange: ITokenRange | null;
}

/**
 * Get the source span for a token range.
 */
export function getSpanForRange(doc: ICstDocument, range: ITokenRange): ISourceSpan {
  const startToken = doc.tokens[range.start];
  const endToken = doc.tokens[range.end - 1] ?? startToken;
  return {
    start: startToken?.span.start ?? { offset: 0, line: 0, column: 0 },
    end: endToken?.span.end ?? { offset: 0, line: 0, column: 0 },
  };
}

/**
 * Get the directive name from a CST directive.
 */
export function getDirectiveName(doc: ICstDocument, directive: ICstDirective): string {
  const token = doc.tokens[directive.nameRange.start];
  return token ? String(token.value) : "";
}

/**
 * Get argument tokens for a directive (non-trivia tokens).
 */
export function getDirectiveArgs(doc: ICstDocument, directive: ICstDirective): IToken[] {
  return directive.argRanges.map((range) => doc.tokens[range.start]).filter(Boolean) as IToken[];
}

/**
 * Serialize a CST document back to source text (byte-identical round-trip).
 */
export function serializeCst(doc: ICstDocument): string {
  return doc.tokens.map((t) => t.text).join("");
}

/**
 * Serialize a token range to source text.
 */
export function serializeRange(doc: ICstDocument, range: ITokenRange): string {
  return doc.tokens
    .slice(range.start, range.end)
    .map((t) => t.text)
    .join("");
}

/**
 * Serialize a directive to source text.
 */
export function serializeDirective(doc: ICstDocument, directive: ICstDirective): string {
  return serializeRange(doc, directive.tokenRange);
}

/**
 * Create a document from tokens and source.
 */
export function createDocument(
  tokens: IToken[],
  children: ICstDirective[],
  source: string,
  sourceId?: string,
): ICstDocument {
  const tokenRange: ITokenRange = {
    start: 0,
    end: tokens.length,
  };
  return {
    kind: CstNodeKind.Document,
    tokenRange,
    tokens,
    children,
    source,
    sourceId,
  };
}
