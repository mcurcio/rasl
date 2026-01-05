/**
 * Lexer for config files.
 *
 * Key features:
 * - Preserves all tokens including trivia for byte-identical round-tripping
 * - Newline is structural (terminates directives)
 * - Word tokens include dots (nginx-style)
 * - Structured diagnostics with stable codes
 */

import {
  DiagnosticCode,
  DiagnosticSeverity,
  type IDiagnostic,
  type ILexResult,
  type ISourceLocation,
  type ISourceSpan,
  type IToken,
  TokenType,
} from "./tokens.js";

/**
 * Lexer for config files.
 */
export class Lexer {
  private readonly _source: string;
  private readonly _sourceId?: string;
  private _pos = 0;
  private _line = 0;
  private _column = 0;

  constructor(source: string, sourceId?: string) {
    this._source = source;
    this._sourceId = sourceId;
  }

  /**
   * Tokenize the entire source, preserving all tokens including trivia.
   */
  lex(): ILexResult {
    const tokens: IToken[] = [];
    const errors: IDiagnostic[] = [];

    while (!this._atEnd()) {
      const result = this._nextToken();
      if (result.token) {
        tokens.push(result.token);
      }
      if (result.error) {
        errors.push(result.error);
      }
    }

    tokens.push(this._makeToken(TokenType.Eof, "", ""));
    return { tokens, errors };
  }

  private _atEnd(): boolean {
    return this._pos >= this._source.length;
  }

  private _peek(offset = 0): string {
    const idx = this._pos + offset;
    if (idx >= this._source.length) return "\0";
    return this._source[idx];
  }

  private _advance(): string {
    const ch = this._source[this._pos++];
    if (ch === "\n") {
      this._line++;
      this._column = 0;
    } else {
      this._column++;
    }
    return ch;
  }

  private _location(): ISourceLocation {
    return { offset: this._pos, line: this._line, column: this._column };
  }

  private _makeSpan(start: ISourceLocation): ISourceSpan {
    return { start, end: this._location() };
  }

  private _makeToken(type: TokenType, text: string, value: string | number | boolean, start?: ISourceLocation): IToken {
    const startLoc = start ?? {
      offset: this._pos - text.length,
      line: this._line,
      column: this._column - text.length,
    };
    return {
      type,
      text,
      value,
      span: { start: startLoc, end: this._location() },
    };
  }

  private _makeError(code: DiagnosticCode, message: string, span: ISourceSpan): IDiagnostic {
    return {
      code,
      severity: code.startsWith("W") ? DiagnosticSeverity.Warning : DiagnosticSeverity.Error,
      message,
      span,
      sourceId: this._sourceId,
    };
  }

  private _nextToken(): { token: IToken | null; error: IDiagnostic | null } {
    const start = this._location();
    const ch = this._peek();

    // Whitespace (not newlines)
    if (ch === " " || ch === "\t" || ch === "\r") {
      return { token: this._readWhitespace(start), error: null };
    }

    // Newline (structural)
    if (ch === "\n") {
      this._advance();
      return { token: this._makeToken(TokenType.Newline, "\n", "\n", start), error: null };
    }

    // Line comment (// or #)
    if ((ch === "/" && this._peek(1) === "/") || ch === "#") {
      return { token: this._readLineComment(start), error: null };
    }

    // Block comment
    if (ch === "/" && this._peek(1) === "*") {
      return this._readBlockComment(start);
    }

    // Single-character tokens
    switch (ch) {
      case "{":
        this._advance();
        return { token: this._makeToken(TokenType.LeftBrace, "{", "{", start), error: null };
      case "}":
        this._advance();
        return { token: this._makeToken(TokenType.RightBrace, "}", "}", start), error: null };
      case "[":
        this._advance();
        return { token: this._makeToken(TokenType.LeftBracket, "[", "[", start), error: null };
      case "]":
        this._advance();
        return { token: this._makeToken(TokenType.RightBracket, "]", "]", start), error: null };
      case ";":
        this._advance();
        return { token: this._makeToken(TokenType.Semicolon, ";", ";", start), error: null };
      case ":":
        this._advance();
        return { token: this._makeToken(TokenType.Colon, ":", ":", start), error: null };
      case ",":
        this._advance();
        return { token: this._makeToken(TokenType.Comma, ",", ",", start), error: null };
    }

    // String literals
    if (ch === '"' || ch === "'") {
      return this._readString(ch, start);
    }

    // Numbers (including negative)
    if (this._isDigit(ch) || (ch === "-" && this._isDigit(this._peek(1)))) {
      // Disambiguate dotted "words" that start with digits (e.g. `127.0.0.1`, `1.2.3`).
      // These are common in nginx-style configs (IPs, versions, host:port, etc.).
      if (this._hasExtraDotAfterNumberLike()) {
        return { token: this._readWord(start), error: null };
      }
      return { token: this._readNumber(start), error: null };
    }

    // Words (identifiers with dots)
    if (this._isWordStart(ch)) {
      return { token: this._readWord(start), error: null };
    }

    // Unknown character - emit error token
    this._advance();
    const span = this._makeSpan(start);
    return {
      token: this._makeToken(TokenType.Error, ch, ch, start),
      error: this._makeError(DiagnosticCode.UnexpectedCharacter, `Unexpected character: '${ch}'`, span),
    };
  }

  private _readWhitespace(start: ISourceLocation): IToken {
    let text = "";
    while (!this._atEnd()) {
      const ch = this._peek();
      if (ch === " " || ch === "\t" || ch === "\r") {
        text += this._advance();
      } else {
        break;
      }
    }
    return this._makeToken(TokenType.Whitespace, text, text, start);
  }

  private _readLineComment(start: ISourceLocation): IToken {
    let text = "";
    // Consume comment prefix (// or #)
    if (this._peek() === "#") {
      text += this._advance();
    } else {
      text += this._advance(); // /
      text += this._advance(); // /
    }
    // Consume until newline (but not the newline itself)
    while (!this._atEnd() && this._peek() !== "\n") {
      text += this._advance();
    }
    return this._makeToken(TokenType.LineComment, text, text, start);
  }

  private _readBlockComment(start: ISourceLocation): { token: IToken; error: IDiagnostic | null } {
    let text = "";
    // Consume /*
    text += this._advance();
    text += this._advance();

    while (!this._atEnd()) {
      if (this._peek() === "*" && this._peek(1) === "/") {
        text += this._advance(); // *
        text += this._advance(); // /
        return { token: this._makeToken(TokenType.BlockComment, text, text, start), error: null };
      }
      text += this._advance();
    }

    // Unterminated block comment
    const span = this._makeSpan(start);
    return {
      token: this._makeToken(TokenType.BlockComment, text, text, start),
      error: this._makeError(DiagnosticCode.UnterminatedBlockComment, "Unterminated block comment", span),
    };
  }

  private _readString(quote: string, start: ISourceLocation): { token: IToken; error: IDiagnostic | null } {
    let text = "";
    let value = "";
    let error: IDiagnostic | null = null;

    text += this._advance(); // Opening quote

    while (!this._atEnd() && this._peek() !== quote) {
      if (this._peek() === "\n") {
        // Newline in string - unterminated
        break;
      }

      if (this._peek() === "\\") {
        const escapeStart = this._location();
        text += this._advance(); // backslash

        if (this._atEnd()) break;

        const escaped = this._peek();
        text += this._advance();

        switch (escaped) {
          case "n":
            value += "\n";
            break;
          case "t":
            value += "\t";
            break;
          case "r":
            value += "\r";
            break;
          case "\\":
            value += "\\";
            break;
          case '"':
            value += '"';
            break;
          case "'":
            value += "'";
            break;
          default:
            // Invalid escape - use literal character but warn
            value += escaped;
            if (!error) {
              error = this._makeError(DiagnosticCode.InvalidEscapeSequence, `Invalid escape sequence: \\${escaped}`, {
                start: escapeStart,
                end: this._location(),
              });
            }
        }
      } else {
        const ch = this._advance();
        text += ch;
        value += ch;
      }
    }

    if (this._atEnd() || this._peek() === "\n") {
      // Unterminated string
      const span = this._makeSpan(start);
      return {
        token: this._makeToken(TokenType.String, text, value, start),
        error: this._makeError(DiagnosticCode.UnterminatedString, "Unterminated string", span),
      };
    }

    text += this._advance(); // Closing quote
    return { token: this._makeToken(TokenType.String, text, value, start), error };
  }

  private _readNumber(start: ISourceLocation): IToken {
    let text = "";

    // Optional negative sign
    if (this._peek() === "-") {
      text += this._advance();
    }

    // Integer part
    while (this._isDigit(this._peek())) {
      text += this._advance();
    }

    // Decimal part
    if (this._peek() === "." && this._isDigit(this._peek(1))) {
      text += this._advance(); // .
      while (this._isDigit(this._peek())) {
        text += this._advance();
      }
    }

    // Exponent
    if (this._peek() === "e" || this._peek() === "E") {
      text += this._advance();
      if (this._peek() === "+" || this._peek() === "-") {
        text += this._advance();
      }
      while (this._isDigit(this._peek())) {
        text += this._advance();
      }
    }

    const value = parseFloat(text);
    return this._makeToken(TokenType.Number, text, value, start);
  }

  private _readWord(start: ISourceLocation): IToken {
    let text = "";

    while (this._isWordChar(this._peek())) {
      text += this._advance();
    }

    // Check for boolean keywords
    if (text === "true") {
      return this._makeToken(TokenType.Word, text, true, start);
    }
    if (text === "false") {
      return this._makeToken(TokenType.Word, text, false, start);
    }

    return this._makeToken(TokenType.Word, text, text, start);
  }

  private _hasExtraDotAfterNumberLike(): boolean {
    let idx = this._pos;

    // Optional negative sign
    if (this._source[idx] === "-") idx++;

    // Integer part
    let sawDigit = false;
    while (idx < this._source.length && this._isDigit(this._source[idx]!)) {
      sawDigit = true;
      idx++;
    }
    if (!sawDigit) return false;

    // Optional decimal part (only one)
    if (this._source[idx] === "." && this._isDigit(this._source[idx + 1] ?? "\0")) {
      idx++; // .
      while (idx < this._source.length && this._isDigit(this._source[idx]!)) idx++;
    }

    // Optional exponent
    if (this._source[idx] === "e" || this._source[idx] === "E") {
      const expStart = idx;
      idx++; // e/E
      if (this._source[idx] === "+" || this._source[idx] === "-") idx++;
      let sawExpDigit = false;
      while (idx < this._source.length && this._isDigit(this._source[idx]!)) {
        sawExpDigit = true;
        idx++;
      }
      if (!sawExpDigit) idx = expStart;
    }

    // A second dot indicates this is not a numeric literal (e.g. IP address).
    return this._source[idx] === ".";
  }

  private _isDigit(ch: string): boolean {
    return ch >= "0" && ch <= "9";
  }

  private _isWordStart(ch: string): boolean {
    return (
      (ch >= "a" && ch <= "z") ||
      (ch >= "A" && ch <= "Z") ||
      this._isDigit(ch) ||
      ch === "_" ||
      ch === "/" ||
      ch === "."
    );
  }

  private _isWordChar(ch: string): boolean {
    return this._isWordStart(ch) || ch === "-" || ch === ":" || ch === "@";
  }
}

/**
 * Tokenize a source string, preserving all tokens for round-tripping.
 */
export function lex(source: string, sourceId?: string): ILexResult {
  return new Lexer(source, sourceId).lex();
}
