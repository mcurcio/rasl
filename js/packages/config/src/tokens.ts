/**
 * Token types for RASL config lexer.
 */

/**
 * Token type enumeration.
 */
export const TokenType = {
  // Keywords
  Node: 'node',
  Connect: 'connect',
  Fill: 'fill',
  Include: 'include',

  // Literals
  Identifier: 'identifier',
  String: 'string',
  Number: 'number',
  Boolean: 'boolean',

  // Punctuation
  LeftBrace: 'left_brace',
  RightBrace: 'right_brace',
  LeftBracket: 'left_bracket',
  RightBracket: 'right_bracket',
  LeftParen: 'left_paren',
  RightParen: 'right_paren',
  Semicolon: 'semicolon',
  Colon: 'colon',
  Comma: 'comma',
  Dot: 'dot',

  // Operators
  Slice: 'slice',           // [start:end]

  // Trivia (preserved for round-tripping)
  Whitespace: 'whitespace',
  Newline: 'newline',
  LineComment: 'line_comment',     // // comment
  BlockComment: 'block_comment',   // /* comment */

  // Special
  Eof: 'eof',
  Error: 'error',
} as const;
export type TokenType = (typeof TokenType)[keyof typeof TokenType];

/**
 * Token with source location.
 */
export interface IToken {
  type: TokenType;
  value: string;
  span: ITokenSpan;
}

/**
 * Token source location.
 */
export interface ITokenSpan {
  start: number;
  end: number;
  line: number;
  column: number;
}

/**
 * Lexer result.
 */
export interface ILexResult {
  tokens: IToken[];
  errors: ILexError[];
}

/**
 * Lexer error.
 */
export interface ILexError {
  message: string;
  line: number;
  column: number;
  span: ITokenSpan;
}

/**
 * Check if a token type is a keyword.
 */
export function isKeyword(type: TokenType): boolean {
  return (
    type === TokenType.Node ||
    type === TokenType.Connect ||
    type === TokenType.Fill ||
    type === TokenType.Include
  );
}

/**
 * Check if a token type is trivia (whitespace/comments).
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
 * Keyword lookup table.
 */
export const Keywords: Record<string, TokenType> = {
  node: TokenType.Node,
  connect: TokenType.Connect,
  fill: TokenType.Fill,
  include: TokenType.Include,
  true: TokenType.Boolean,
  false: TokenType.Boolean,
};
