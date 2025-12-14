/**
 * Token types for config lexer.
 */
/**
 * Token type enumeration.
 */
export declare const TokenType: {
    readonly Identifier: "identifier";
    readonly String: "string";
    readonly Number: "number";
    readonly Boolean: "boolean";
    readonly LeftBrace: "left_brace";
    readonly RightBrace: "right_brace";
    readonly LeftBracket: "left_bracket";
    readonly RightBracket: "right_bracket";
    readonly LeftParen: "left_paren";
    readonly RightParen: "right_paren";
    readonly Semicolon: "semicolon";
    readonly Colon: "colon";
    readonly Comma: "comma";
    readonly Dot: "dot";
    readonly Whitespace: "whitespace";
    readonly Newline: "newline";
    readonly LineComment: "line_comment";
    readonly BlockComment: "block_comment";
    readonly Eof: "eof";
    readonly Error: "error";
};
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
 * Check if a token type is trivia (whitespace/comments).
 */
export declare function isTrivia(type: TokenType): boolean;
/**
 * Check if a token type is a comment.
 */
export declare function isComment(type: TokenType): boolean;
/**
 * Keyword lookup table.
 *
 * This is intentionally minimal to keep @rasl/config schema-agnostic.
 */
export declare const Keywords: Record<string, TokenType>;
//# sourceMappingURL=tokens.d.ts.map