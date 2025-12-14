/**
 * Lexer for RASL config files (nginx-style syntax).
 */
import { TokenType, Keywords } from './tokens.js';
/**
 * Lexer for RASL configuration files.
 */
export class Lexer {
    _source;
    _pos = 0;
    _line = 1;
    _column = 0;
    _lineStart = 0;
    constructor(source) {
        this._source = source;
    }
    /**
     * Tokenize the entire source.
     */
    lex() {
        const tokens = [];
        const errors = [];
        while (!this._atEnd()) {
            try {
                const token = this._nextToken();
                if (token) {
                    tokens.push(token);
                }
            }
            catch (e) {
                const err = e;
                errors.push({
                    message: err.message,
                    line: this._line,
                    column: this._column,
                    span: { start: this._pos, end: this._pos + 1, line: this._line, column: this._column },
                });
                this._advance(); // Skip problematic character
            }
        }
        tokens.push(this._makeToken(TokenType.Eof, ''));
        return { tokens, errors };
    }
    _atEnd() {
        return this._pos >= this._source.length;
    }
    _peek() {
        if (this._atEnd())
            return '\0';
        return this._source[this._pos];
    }
    _peekNext() {
        if (this._pos + 1 >= this._source.length)
            return '\0';
        return this._source[this._pos + 1];
    }
    _advance() {
        const ch = this._source[this._pos++];
        if (ch === '\n') {
            this._line++;
            this._lineStart = this._pos;
            this._column = 0;
        }
        else {
            this._column++;
        }
        return ch;
    }
    _makeToken(type, value, startPos) {
        const start = startPos ?? this._pos - value.length;
        return {
            type,
            value,
            span: {
                start,
                end: this._pos,
                line: this._line,
                column: start - this._lineStart,
            },
        };
    }
    _nextToken() {
        this._skipWhitespaceAndComments();
        if (this._atEnd())
            return null;
        const startPos = this._pos;
        const ch = this._peek();
        // Single-character tokens
        switch (ch) {
            case '{':
                this._advance();
                return this._makeToken(TokenType.LeftBrace, '{', startPos);
            case '}':
                this._advance();
                return this._makeToken(TokenType.RightBrace, '}', startPos);
            case '[':
                this._advance();
                return this._makeToken(TokenType.LeftBracket, '[', startPos);
            case ']':
                this._advance();
                return this._makeToken(TokenType.RightBracket, ']', startPos);
            case '(':
                this._advance();
                return this._makeToken(TokenType.LeftParen, '(', startPos);
            case ')':
                this._advance();
                return this._makeToken(TokenType.RightParen, ')', startPos);
            case ';':
                this._advance();
                return this._makeToken(TokenType.Semicolon, ';', startPos);
            case ':':
                this._advance();
                return this._makeToken(TokenType.Colon, ':', startPos);
            case ',':
                this._advance();
                return this._makeToken(TokenType.Comma, ',', startPos);
            case '.':
                this._advance();
                return this._makeToken(TokenType.Dot, '.', startPos);
        }
        // String literals
        if (ch === '"' || ch === "'") {
            return this._readString(ch);
        }
        // Numbers (including negative)
        if (this._isDigit(ch) || (ch === '-' && this._isDigit(this._peekNext()))) {
            return this._readNumber();
        }
        // Identifiers and keywords
        if (this._isAlpha(ch)) {
            return this._readIdentifier();
        }
        throw new Error(`Unexpected character: '${ch}'`);
    }
    _skipWhitespaceAndComments() {
        while (!this._atEnd()) {
            const ch = this._peek();
            if (ch === ' ' || ch === '\t' || ch === '\r' || ch === '\n') {
                this._advance();
                continue;
            }
            // Line comment
            if (ch === '/' && this._peekNext() === '/') {
                while (!this._atEnd() && this._peek() !== '\n') {
                    this._advance();
                }
                continue;
            }
            // Block comment
            if (ch === '/' && this._peekNext() === '*') {
                this._advance(); // /
                this._advance(); // *
                while (!this._atEnd()) {
                    if (this._peek() === '*' && this._peekNext() === '/') {
                        this._advance(); // *
                        this._advance(); // /
                        break;
                    }
                    this._advance();
                }
                continue;
            }
            // Hash comment (nginx style)
            if (ch === '#') {
                while (!this._atEnd() && this._peek() !== '\n') {
                    this._advance();
                }
                continue;
            }
            break;
        }
    }
    _readString(quote) {
        const startPos = this._pos;
        this._advance(); // Opening quote
        let value = '';
        while (!this._atEnd() && this._peek() !== quote) {
            if (this._peek() === '\\') {
                this._advance();
                if (!this._atEnd()) {
                    const escaped = this._advance();
                    switch (escaped) {
                        case 'n':
                            value += '\n';
                            break;
                        case 't':
                            value += '\t';
                            break;
                        case 'r':
                            value += '\r';
                            break;
                        case '\\':
                            value += '\\';
                            break;
                        case '"':
                            value += '"';
                            break;
                        case "'":
                            value += "'";
                            break;
                        default: value += escaped;
                    }
                }
            }
            else {
                value += this._advance();
            }
        }
        if (this._atEnd()) {
            throw new Error('Unterminated string');
        }
        this._advance(); // Closing quote
        return this._makeToken(TokenType.String, value, startPos);
    }
    _readNumber() {
        const startPos = this._pos;
        let value = '';
        if (this._peek() === '-') {
            value += this._advance();
        }
        while (this._isDigit(this._peek())) {
            value += this._advance();
        }
        // Decimal part
        if (this._peek() === '.' && this._isDigit(this._peekNext())) {
            value += this._advance(); // .
            while (this._isDigit(this._peek())) {
                value += this._advance();
            }
        }
        // Exponent
        if (this._peek() === 'e' || this._peek() === 'E') {
            value += this._advance();
            if (this._peek() === '+' || this._peek() === '-') {
                value += this._advance();
            }
            while (this._isDigit(this._peek())) {
                value += this._advance();
            }
        }
        return this._makeToken(TokenType.Number, value, startPos);
    }
    _readIdentifier() {
        const startPos = this._pos;
        let value = '';
        while (this._isAlphaNumeric(this._peek())) {
            value += this._advance();
        }
        // Check for keywords
        const keywordType = Keywords[value];
        if (keywordType) {
            if (keywordType === TokenType.Boolean) {
                return this._makeToken(TokenType.Boolean, value, startPos);
            }
            return this._makeToken(keywordType, value, startPos);
        }
        return this._makeToken(TokenType.Identifier, value, startPos);
    }
    _isDigit(ch) {
        return ch >= '0' && ch <= '9';
    }
    _isAlpha(ch) {
        return (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || ch === '_';
    }
    _isAlphaNumeric(ch) {
        return this._isAlpha(ch) || this._isDigit(ch);
    }
}
/**
 * Tokenize a source string.
 */
export function lex(source) {
    return new Lexer(source).lex();
}
//# sourceMappingURL=lexer.js.map