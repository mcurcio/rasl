/**
 * Token types for the config lexer.
 *
 * Key properties:
 * - Word token includes dots (nginx-style: `server.name` is one word)
 * - Newline is structural (terminates directives)
 * - All trivia preserved in token stream for round-tripping
 */

/**
 * Token type enumeration.
 */
export const TokenType = {
  // Literals
  Word: "word", // Identifier with dots: letters/digits/underscores/dots
  String: "string", // Quoted string (single or double)
  Number: "number", // Numeric literal

  // Punctuation
  LeftBrace: "left_brace",
  RightBrace: "right_brace",
  LeftBracket: "left_bracket",
  RightBracket: "right_bracket",
  Semicolon: "semicolon",
  Colon: "colon",
  Comma: "comma",

  // Trivia (preserved for round-tripping)
  Whitespace: "whitespace", // Spaces and tabs (not newlines)
  Newline: "newline", // Structural: terminates directives
  LineComment: "line_comment",
  BlockComment: "block_comment",

  // Special
  Eof: "eof",
  Error: "error",
} as const;
export type TokenType = (typeof TokenType)[keyof typeof TokenType];

/**
 * 0-based source location.
 */
export interface ISourceLocation {
  offset: number; // Byte offset from start of source
  line: number; // 0-based line number
  column: number; // 0-based column number
}

/**
 * Source span with start and end locations.
 */
export interface ISourceSpan {
  start: ISourceLocation;
  end: ISourceLocation;
}

/**
 * Token with exact source text and location.
 */
export interface IToken {
  type: TokenType;
  /** Raw source text (exact lexeme for round-tripping) */
  text: string;
  /** Parsed/decoded value (e.g., unescaped string content) */
  value: string | number | boolean;
  span: ISourceSpan;
}

/**
 * Lexer result.
 */
export interface ILexResult {
  /** Full token stream including trivia */
  tokens: IToken[];
  errors: IDiagnostic[];
}

/**
 * Diagnostic codes for stable cross-language error identification.
 */
export const DiagnosticCode = {
  // Lexer errors (1xxx)
  UnterminatedString: "E1001",
  UnterminatedBlockComment: "E1002",
  UnexpectedCharacter: "E1003",
  InvalidEscapeSequence: "W1004",
  InvalidNumber: "E1005",

  // Parser errors (2xxx)
  UnexpectedToken: "E2001",
  ExpectedDirectiveName: "E2002",
  ExpectedClosingBrace: "E2003",
  ExpectedClosingBracket: "E2004",
  ExpectedSemicolonOrNewline: "E2005",
  ExpectedStringLiteral: "E2006",

  // Include errors (3xxx)
  IncludeNotFound: "E3001",
  IncludeCycle: "E3002",
  IncludeDepthExceeded: "E3003",
  IncludeResolverFailed: "E3004",
  IncludeNoMatches: "W3005",
} as const;
export type DiagnosticCode = (typeof DiagnosticCode)[keyof typeof DiagnosticCode];

/**
 * Diagnostic severity.
 */
export const DiagnosticSeverity = {
  Error: "error",
  Warning: "warning",
  Info: "info",
} as const;
export type DiagnosticSeverity = (typeof DiagnosticSeverity)[keyof typeof DiagnosticSeverity];

/**
 * Structured diagnostic with stable code.
 */
export interface IDiagnostic {
  code: DiagnosticCode;
  severity: DiagnosticSeverity;
  message: string;
  span: ISourceSpan;
  /** Optional source file identifier */
  sourceId?: string;
}

/**
 * Check if a token type is trivia (whitespace/comments/newlines).
 */
export function isTrivia(type: TokenType): boolean {
  return (
    type === TokenType.Whitespace ||
    type === TokenType.Newline ||
    type === TokenType.LineComment ||
    type === TokenType.BlockComment
  );
}

/**
 * Check if a token type is a comment.
 */
export function isComment(type: TokenType): boolean {
  return type === TokenType.LineComment || type === TokenType.BlockComment;
}

/**
 * Check if a token type is whitespace (not newline).
 */
export function isWhitespace(type: TokenType): boolean {
  return type === TokenType.Whitespace;
}

/**
 * Check if a token terminates a directive (newline or semicolon).
 */
export function isTerminator(type: TokenType): boolean {
  return type === TokenType.Newline || type === TokenType.Semicolon;
}
