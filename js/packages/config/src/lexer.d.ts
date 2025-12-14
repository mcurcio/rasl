/**
 * Lexer for RASL config files (nginx-style syntax).
 */
import { type ILexResult } from './tokens.js';
/**
 * Lexer for RASL configuration files.
 */
export declare class Lexer {
    private readonly _source;
    private _pos;
    private _line;
    private _column;
    private _lineStart;
    constructor(source: string);
    /**
     * Tokenize the entire source.
     */
    lex(): ILexResult;
    private _atEnd;
    private _peek;
    private _peekNext;
    private _advance;
    private _makeToken;
    private _nextToken;
    private _skipWhitespaceAndComments;
    private _readString;
    private _readNumber;
    private _readIdentifier;
    private _isDigit;
    private _isAlpha;
    private _isAlphaNumeric;
}
/**
 * Tokenize a source string.
 */
export declare function lex(source: string): ILexResult;
//# sourceMappingURL=lexer.d.ts.map