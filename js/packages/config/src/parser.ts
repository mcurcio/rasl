/**
 * Parser for config files.
 *
 * Key features:
 * - Builds CST with token-range references (not copies)
 * - Newline terminates directives (semicolons optional)
 * - Multi-line bracket lists allowed
 * - Structured diagnostics with stable codes
 */

import { createDocument, CstNodeKind, type ICstDirective, type ICstDocument, type ITokenRange } from "./cst.js";
import { lex } from "./lexer.js";
import {
  DiagnosticCode,
  DiagnosticSeverity,
  type IDiagnostic,
  isTerminator,
  isTrivia,
  type IToken,
  TokenType,
} from "./tokens.js";

/**
 * Parser configuration options.
 */
export interface IParseDocumentConfig {
  /** Optional source identifier for diagnostics */
  sourceId?: string;
}

/**
 * Result of parsing a config file.
 */
export interface IParseResult {
  /** Concrete Syntax Tree (owns token stream for round-tripping) */
  cst: ICstDocument;
  /** Parse errors */
  errors: IDiagnostic[];
  /** Parse warnings */
  warnings: IDiagnostic[];
}

/**
 * Parser for config files.
 */
class Parser {
  private readonly _tokens: IToken[];
  private readonly _sourceId?: string;
  private _pos = 0;
  private readonly _errors: IDiagnostic[] = [];
  private readonly _warnings: IDiagnostic[] = [];

  constructor(tokens: IToken[], sourceId?: string) {
    this._tokens = tokens;
    this._sourceId = sourceId;
  }

  parse(): { children: ICstDirective[]; errors: IDiagnostic[]; warnings: IDiagnostic[] } {
    const children: ICstDirective[] = [];

    // Skip leading trivia
    this._skipTrivia();

    while (!this._atEnd()) {
      try {
        const directive = this._parseDirective();
        if (directive) {
          children.push(directive);
        }
      } catch (e) {
        const err = e as Error;
        const current = this._current();
        this._errors.push({
          code: DiagnosticCode.UnexpectedToken,
          severity: DiagnosticSeverity.Error,
          message: err.message,
          span: current.span,
          sourceId: this._sourceId,
        });
        this._synchronize();
      }
      this._skipTrivia();
    }

    return { children, errors: this._errors, warnings: this._warnings };
  }

  private _atEnd(): boolean {
    return this._current().type === TokenType.Eof;
  }

  private _current(): IToken {
    return this._tokens[this._pos] ?? this._eofToken();
  }

  private _eofToken(): IToken {
    return {
      type: TokenType.Eof,
      text: "",
      value: "",
      span: { start: { offset: 0, line: 0, column: 0 }, end: { offset: 0, line: 0, column: 0 } },
    };
  }

  private _advance(): IToken {
    if (!this._atEnd()) this._pos++;
    return this._tokens[this._pos - 1];
  }

  private _check(type: TokenType): boolean {
    return this._current().type === type;
  }

  private _skipTrivia(): void {
    while (isTrivia(this._current().type)) {
      this._advance();
    }
  }

  private _skipNonNewlineTrivia(): void {
    while (
      this._current().type === TokenType.Whitespace ||
      this._current().type === TokenType.LineComment ||
      this._current().type === TokenType.BlockComment
    ) {
      this._advance();
    }
  }

  private _synchronize(): void {
    this._advance();
    while (!this._atEnd()) {
      const prev = this._tokens[this._pos - 1];
      if (prev?.type === TokenType.Semicolon || prev?.type === TokenType.Newline) return;
      if (prev?.type === TokenType.RightBrace) return;
      if (this._check(TokenType.Word)) return;
      this._advance();
    }
  }

  private _parseDirective(): ICstDirective | null {
    const startPos = this._pos;

    // Expect directive name (Word token)
    if (!this._check(TokenType.Word)) {
      // Skip stray terminators
      if (this._check(TokenType.Semicolon) || this._check(TokenType.Newline)) {
        this._advance();
        return null;
      }
      throw new Error(`Expected directive name, got ${this._current().type}`);
    }

    const nameStart = this._pos;
    this._advance();
    const nameRange: ITokenRange = { start: nameStart, end: this._pos };

    // Parse arguments until we hit { or terminator
    const argRanges: ITokenRange[] = [];
    let bracketDepth = 0;

    while (!this._atEnd()) {
      this._skipNonNewlineTrivia();

      const current = this._current();

      // Opening brace starts body
      if (current.type === TokenType.LeftBrace && bracketDepth === 0) {
        break;
      }

      // Terminator ends directive (unless inside brackets)
      if (isTerminator(current.type) && bracketDepth === 0) {
        break;
      }

      // Closing brace without opening - end of parent block
      if (current.type === TokenType.RightBrace && bracketDepth === 0) {
        break;
      }

      // Track bracket depth for multi-line lists
      if (current.type === TokenType.LeftBracket) {
        bracketDepth++;
      } else if (current.type === TokenType.RightBracket) {
        bracketDepth--;
      }

      // Collect argument token
      if (!isTrivia(current.type)) {
        const argStart = this._pos;
        this._advance();
        argRanges.push({ start: argStart, end: this._pos });
      } else {
        this._advance();
      }
    }

    // Parse body if present
    let body: ICstDirective[] | null = null;
    let bodyRange: ITokenRange | null = null;

    this._skipNonNewlineTrivia();

    if (this._check(TokenType.LeftBrace)) {
      const bodyStart = this._pos;
      this._advance(); // consume {

      body = [];
      this._skipTrivia();

      while (!this._atEnd() && !this._check(TokenType.RightBrace)) {
        const child = this._parseDirective();
        if (child) {
          body.push(child);
        }
        this._skipTrivia();
      }

      if (this._check(TokenType.RightBrace)) {
        this._advance(); // consume }
      } else {
        this._errors.push({
          code: DiagnosticCode.ExpectedClosingBrace,
          severity: DiagnosticSeverity.Error,
          message: "Expected closing brace",
          span: this._current().span,
          sourceId: this._sourceId,
        });
      }

      bodyRange = { start: bodyStart, end: this._pos };
    } else {
      // Consume terminator (semicolon or newline)
      if (this._check(TokenType.Semicolon) || this._check(TokenType.Newline)) {
        this._advance();
      }
    }

    const tokenRange: ITokenRange = { start: startPos, end: this._pos };

    return {
      kind: CstNodeKind.Directive,
      tokenRange,
      nameRange,
      argRanges,
      body,
      bodyRange,
    };
  }
}

/**
 * Parse a config file.
 */
export function parseDocument(source: string, config?: IParseDocumentConfig): IParseResult {
  const sourceId = config?.sourceId;
  const lexResult = lex(source, sourceId);

  const parser = new Parser(lexResult.tokens, sourceId);
  const { children, errors: parseErrors, warnings: parseWarnings } = parser.parse();

  const cst = createDocument(lexResult.tokens, children, source, sourceId);

  const lexWarnings = lexResult.errors.filter((d) => d.severity === DiagnosticSeverity.Warning);
  const lexErrors = lexResult.errors.filter((d) => d.severity === DiagnosticSeverity.Error);

  return {
    cst,
    errors: [...lexErrors, ...parseErrors],
    warnings: [...lexWarnings, ...parseWarnings],
  };
}
