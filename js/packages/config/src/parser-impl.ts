/**
 * Parser implementation for RASL config files.
 * Builds CST and AST from token stream.
 */

import { TokenType, type IToken, isTrivia } from './tokens.js';
import { lex } from './lexer.js';
import {
  CstNodeKind,
  type ICstDocument,
  type ICstDirective,
  type ISourceSpan,
} from './cst.js';
import type { IParseResult, IParseError, IParseConfig } from './parser.js';

/**
 * Parser for RASL config files.
 */
class Parser {
  private readonly _tokens: IToken[];
  private _pos = 0;
  private readonly _errors: IParseError[] = [];
  private readonly _warnings: IParseError[] = [];

  constructor(tokens: IToken[]) {
    // Filter out trivia tokens for parsing
    this._tokens = tokens.filter((t) => !isTrivia(t.type));
  }

  parse(): { cst: ICstDocument; errors: IParseError[]; warnings: IParseError[] } {
    const children: ICstDirective[] = [];

    while (!this._atEnd()) {
      try {
        const directive = this._parseTopLevel();
        if (directive) children.push(directive);
      } catch (e) {
        const err = e as Error;
        this._errors.push({
          message: err.message,
          line: this._current().span.line,
          column: this._current().span.column,
        });
        this._synchronize();
      }
    }

    const cst: ICstDocument = {
      kind: CstNodeKind.Document,
      span: { start: 0, end: this._pos, line: 1, column: 0 },
      children,
    };

    return { cst, errors: this._errors, warnings: this._warnings };
  }

  private _atEnd(): boolean {
    return this._current().type === TokenType.Eof;
  }

  private _current(): IToken {
    return this._tokens[this._pos] ?? { type: TokenType.Eof, value: '', span: { start: 0, end: 0, line: 0, column: 0 } };
  }

  private _advance(): IToken {
    if (!this._atEnd()) this._pos++;
    return this._tokens[this._pos - 1];
  }

  private _check(type: TokenType): boolean {
    return this._current().type === type;
  }

  private _match(...types: TokenType[]): boolean {
    for (const type of types) {
      if (this._check(type)) {
        this._advance();
        return true;
      }
    }
    return false;
  }

  private _consume(type: TokenType, message: string): IToken {
    if (this._check(type)) return this._advance();
    throw new Error(`${message} at line ${this._current().span.line}`);
  }

  private _synchronize(): void {
    this._advance();
    while (!this._atEnd()) {
      if (this._tokens[this._pos - 1]?.type === TokenType.Semicolon) return;
      if (this._tokens[this._pos - 1]?.type === TokenType.RightBrace) return;
      if (this._check(TokenType.Identifier)) return;
      this._advance();
    }
  }

  private _parseTopLevel(): ICstDirective | null {
    if (this._check(TokenType.Identifier)) {
      return this._parseDirective();
    }
    if (this._match(TokenType.Semicolon)) return null;
    throw new Error(`Unexpected token: ${this._current().value}`);
  }

  private _parseDirective(): ICstDirective {
    const startToken = this._current();
    const name = this._consume(TokenType.Identifier, 'Expected directive name').value;

    const args: IToken[] = [];
    while (!this._check(TokenType.LeftBrace) && !this._check(TokenType.Semicolon) && !this._check(TokenType.RightBrace) && !this._atEnd()) {
      const token = this._advance();
      if (
        token.type === TokenType.Identifier ||
        token.type === TokenType.String ||
        token.type === TokenType.Number ||
        token.type === TokenType.Boolean
      ) {
        args.push(token);
        continue;
      }
      if (token.type === TokenType.Colon) {
        args.push(token);
        continue;
      }
      if (token.type === TokenType.Dot) {
        args.push(token);
        continue;
      }
      if (token.type === TokenType.LeftBracket) {
        args.push(this._parseBracketLiteralToken(token));
        continue;
      }
      if (token.type === TokenType.Comma) {
        args.push(token);
        continue;
      }

      throw new Error(`Unexpected token in directive args: ${token.value}`);
    }

    let body: ICstDirective[] | null = null;
    if (this._match(TokenType.LeftBrace)) {
      body = [];
      while (!this._check(TokenType.RightBrace) && !this._atEnd()) {
        if (this._match(TokenType.Semicolon)) continue;
        body.push(this._parseDirective());
      }
      this._consume(TokenType.RightBrace, 'Expected }');
    } else {
      this._match(TokenType.Semicolon);
    }

    const span: ISourceSpan = {
      start: startToken.span.start,
      end: this._tokens[this._pos - 1]?.span.end ?? startToken.span.end,
      line: startToken.span.line,
      column: startToken.span.column,
    };

    return {
      kind: CstNodeKind.Directive,
      span,
      name,
      args,
      body,
    };
  }

  private _parseBracketLiteralToken(startToken: IToken): IToken {
    // We have already consumed '[', now parse until matching ']'.
    let depth = 1;
    let result = '[';
    const startSpan = startToken.span;
    let endSpan = startSpan;

    while (depth > 0 && !this._atEnd()) {
      const token = this._advance();
      endSpan = token.span;
      if (token.type === TokenType.LeftBracket) {
        depth++;
        result += '[';
        continue;
      }
      if (token.type === TokenType.RightBracket) {
        depth--;
        result += ']';
        continue;
      }
      if (token.type === TokenType.Comma) {
        result += ',';
        continue;
      }
      result += token.value;
    }

    return {
      type: TokenType.String,
      value: result,
      span: {
        start: startSpan.start,
        end: endSpan.end,
        line: startSpan.line,
        column: startSpan.column,
      },
    };
  }
}

/**
 * Parse a RASL config file.
 */
export function parseImpl(source: string, _config?: IParseConfig): IParseResult {
  const lexResult = lex(source);

  if (lexResult.errors.length > 0) {
    return {
      cst: null,
      errors: lexResult.errors,
      warnings: [],
      source,
    };
  }

  const parser = new Parser(lexResult.tokens);
  const { cst, errors, warnings } = parser.parse();

  if (errors.length > 0) {
    return {
      cst,
      errors,
      warnings,
      source,
    };
  }
  return {
    cst,
    errors: [],
    warnings,
    source,
  };
}
