/**
 * Token types for config lexer.
 */
/**
 * Token type enumeration.
 */
export const TokenType = {
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
    // Trivia (preserved for round-tripping)
    Whitespace: 'whitespace',
    Newline: 'newline',
    LineComment: 'line_comment', // // comment
    BlockComment: 'block_comment', // /* comment */
    // Special
    Eof: 'eof',
    Error: 'error',
};
/**
 * Check if a token type is trivia (whitespace/comments).
 */
export function isTrivia(type) {
    return (type === TokenType.Whitespace ||
        type === TokenType.Newline ||
        type === TokenType.LineComment ||
        type === TokenType.BlockComment);
}
/**
 * Check if a token type is a comment.
 */
export function isComment(type) {
    return type === TokenType.LineComment || type === TokenType.BlockComment;
}
/**
 * Keyword lookup table.
 *
 * This is intentionally minimal to keep @rasl/config schema-agnostic.
 */
export const Keywords = {
    true: TokenType.Boolean,
    false: TokenType.Boolean,
};
//# sourceMappingURL=tokens.js.map