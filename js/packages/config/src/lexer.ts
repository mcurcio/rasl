/**
 * Lexer for RASL config files (nginx-style syntax).
 */

import { TokenType, type IToken, type ILexResult, type ILexError, Keywords } from './tokens.js';

/**
 * Lexer for RASL configuration files.
 */
export class Lexer {
  private readonly _source: string;
  private _pos = 0;
  private _line = 1;
  private _column = 0;
  private _lineStart = 0;

  constructor(source: string) {
    this._source = source;
  }

  /**
   * Tokenize the entire source.
   */
  lex(): ILexResult {
    const tokens: IToken[] = [];
    const errors: ILexError[] = [];

    while (!this._atEnd()) {
      try {
        const token = this._nextToken();
        if (token) {
          tokens.push(token);
        }
      } catch (e) {
        const err = e as Error;
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

  private _atEnd(): boolean {
    return this._pos >= this._source.length;
  }

  private _peek(): string {
    if (this._atEnd()) return '\0';
    return this._source[this._pos];
  }

  private _peekNext(): string {
    if (this._pos + 1 >= this._source.length) return '\0';
    return this._source[this._pos + 1];
  }

  private _advance(): string {
    const ch = this._source[this._pos++];
    if (ch === '\n') {
      this._line++;
      this._lineStart = this._pos;
      this._column = 0;
    } else {
      this._column++;
    }
    return ch;
  }

  private _makeToken(type: TokenType, value: string, startPos?: number): IToken {
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

  private _nextToken(): IToken | null {
    this._skipWhitespaceAndComments();
    if (this._atEnd()) return null;

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

  private _skipWhitespaceAndComments(): void {
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

  private _readString(quote: string): IToken {
    const startPos = this._pos;
    this._advance(); // Opening quote
    let value = '';

    while (!this._atEnd() && this._peek() !== quote) {
      if (this._peek() === '\\') {
        this._advance();
        if (!this._atEnd()) {
          const escaped = this._advance();
          switch (escaped) {
            case 'n': value += '\n'; break;
            case 't': value += '\t'; break;
            case 'r': value += '\r'; break;
            case '\\': value += '\\'; break;
            case '"': value += '"'; break;
            case "'": value += "'"; break;
            default: value += escaped;
          }
        }
      } else {
        value += this._advance();
      }
    }

    if (this._atEnd()) {
      throw new Error('Unterminated string');
    }

    this._advance(); // Closing quote
    return this._makeToken(TokenType.String, value, startPos);
  }

  private _readNumber(): IToken {
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

  private _readIdentifier(): IToken {
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

  private _isDigit(ch: string): boolean {
    return ch >= '0' && ch <= '9';
  }

  private _isAlpha(ch: string): boolean {
    return (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || ch === '_';
  }

  private _isAlphaNumeric(ch: string): boolean {
    return this._isAlpha(ch) || this._isDigit(ch);
  }
}

/**
 * Tokenize a source string.
 */
export function lex(source: string): ILexResult {
  return new Lexer(source).lex();
}
