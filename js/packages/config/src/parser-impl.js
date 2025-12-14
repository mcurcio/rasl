/**
 * Parser implementation for RASL config files.
 * Builds CST and AST from token stream.
 */
import { TokenType, isTrivia } from './tokens.js';
import { lex } from './lexer.js';
import { CstNodeKind, } from './cst.js';
/**
 * Parser for RASL config files.
 */
class Parser {
    _tokens;
    _pos = 0;
    _errors = [];
    _warnings = [];
    constructor(tokens) {
        // Filter out trivia tokens for parsing
        this._tokens = tokens.filter((t) => !isTrivia(t.type));
    }
    parse() {
        const children = [];
        while (!this._atEnd()) {
            try {
                const directive = this._parseTopLevel();
                if (directive)
                    children.push(directive);
            }
            catch (e) {
                const err = e;
                this._errors.push({
                    message: err.message,
                    line: this._current().span.line,
                    column: this._current().span.column,
                });
                this._synchronize();
            }
        }
        const cst = {
            kind: CstNodeKind.Document,
            span: { start: 0, end: this._pos, line: 1, column: 0 },
            children,
        };
        return { cst, errors: this._errors, warnings: this._warnings };
    }
    _atEnd() {
        return this._current().type === TokenType.Eof;
    }
    _current() {
        return this._tokens[this._pos] ?? { type: TokenType.Eof, value: '', span: { start: 0, end: 0, line: 0, column: 0 } };
    }
    _advance() {
        if (!this._atEnd())
            this._pos++;
        return this._tokens[this._pos - 1];
    }
    _check(type) {
        return this._current().type === type;
    }
    _match(...types) {
        for (const type of types) {
            if (this._check(type)) {
                this._advance();
                return true;
            }
        }
        return false;
    }
    _consume(type, message) {
        if (this._check(type))
            return this._advance();
        throw new Error(`${message} at line ${this._current().span.line}`);
    }
    _synchronize() {
        this._advance();
        while (!this._atEnd()) {
            if (this._tokens[this._pos - 1]?.type === TokenType.Semicolon)
                return;
            if (this._tokens[this._pos - 1]?.type === TokenType.RightBrace)
                return;
            if (this._check(TokenType.Identifier))
                return;
            this._advance();
        }
    }
    _parseTopLevel() {
        if (this._check(TokenType.Identifier)) {
            return this._parseDirective();
        }
        if (this._match(TokenType.Semicolon))
            return null;
        throw new Error(`Unexpected token: ${this._current().value}`);
    }
    _parseDirective() {
        const startToken = this._current();
        const name = this._consume(TokenType.Identifier, 'Expected directive name').value;
        const args = [];
        while (!this._check(TokenType.LeftBrace) && !this._check(TokenType.Semicolon) && !this._check(TokenType.RightBrace) && !this._atEnd()) {
            const token = this._advance();
            if (token.type === TokenType.Identifier ||
                token.type === TokenType.String ||
                token.type === TokenType.Number ||
                token.type === TokenType.Boolean) {
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
        let body = null;
        if (this._match(TokenType.LeftBrace)) {
            body = [];
            while (!this._check(TokenType.RightBrace) && !this._atEnd()) {
                if (this._match(TokenType.Semicolon))
                    continue;
                body.push(this._parseDirective());
            }
            this._consume(TokenType.RightBrace, 'Expected }');
        }
        else {
            this._match(TokenType.Semicolon);
        }
        const span = {
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
    _parseBracketLiteralToken(startToken) {
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
export function parseImpl(source, _config) {
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
//# sourceMappingURL=parser-impl.js.map