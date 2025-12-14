/**
 * Tests for the RASL config lexer.
 */

import { describe, it, expect } from 'vitest';
import { lex } from './lexer.js';
import { TokenType } from './tokens.js';

describe('Lexer', () => {
  describe('basic tokens', () => {
    it('should tokenize identifiers', () => {
      const result = lex('hello world');
      const tokens = result.tokens.filter((t) => t.type !== TokenType.Eof);
      expect(tokens).toHaveLength(2);
      expect(tokens[0].type).toBe(TokenType.Identifier);
      expect(tokens[0].value).toBe('hello');
      expect(tokens[1].type).toBe(TokenType.Identifier);
      expect(tokens[1].value).toBe('world');
    });

    it('should tokenize numbers', () => {
      const result = lex('42 3.14 -5 1e10');
      const tokens = result.tokens.filter((t) => t.type !== TokenType.Eof);
      expect(tokens).toHaveLength(4);
      expect(tokens[0].type).toBe(TokenType.Number);
      expect(tokens[0].value).toBe('42');
      expect(tokens[1].type).toBe(TokenType.Number);
      expect(tokens[1].value).toBe('3.14');
      expect(tokens[2].type).toBe(TokenType.Number);
      expect(tokens[2].value).toBe('-5');
      expect(tokens[3].type).toBe(TokenType.Number);
      expect(tokens[3].value).toBe('1e10');
    });

    it('should tokenize strings', () => {
      const result = lex('"hello" \'world\'');
      const tokens = result.tokens.filter((t) => t.type !== TokenType.Eof);
      expect(tokens).toHaveLength(2);
      expect(tokens[0].type).toBe(TokenType.String);
      expect(tokens[0].value).toBe('hello');
      expect(tokens[1].type).toBe(TokenType.String);
      expect(tokens[1].value).toBe('world');
    });

    it('should tokenize booleans', () => {
      const result = lex('true false');
      const tokens = result.tokens.filter((t) => t.type !== TokenType.Eof);
      expect(tokens).toHaveLength(2);
      expect(tokens[0].type).toBe(TokenType.Boolean);
      expect(tokens[0].value).toBe('true');
      expect(tokens[1].type).toBe(TokenType.Boolean);
      expect(tokens[1].value).toBe('false');
    });

    it('should tokenize punctuation', () => {
      const result = lex('{ } [ ] ( ) ; : , .');
      const tokens = result.tokens.filter((t) => t.type !== TokenType.Eof);
      expect(tokens).toHaveLength(10);
      expect(tokens[0].type).toBe(TokenType.LeftBrace);
      expect(tokens[1].type).toBe(TokenType.RightBrace);
      expect(tokens[2].type).toBe(TokenType.LeftBracket);
      expect(tokens[3].type).toBe(TokenType.RightBracket);
      expect(tokens[4].type).toBe(TokenType.LeftParen);
      expect(tokens[5].type).toBe(TokenType.RightParen);
      expect(tokens[6].type).toBe(TokenType.Semicolon);
      expect(tokens[7].type).toBe(TokenType.Colon);
      expect(tokens[8].type).toBe(TokenType.Comma);
      expect(tokens[9].type).toBe(TokenType.Dot);
    });
  });

  describe('comments', () => {
    it('should skip line comments', () => {
      const result = lex('hello // this is a comment\nworld');
      const tokens = result.tokens.filter((t) => t.type !== TokenType.Eof);
      expect(tokens).toHaveLength(2);
      expect(tokens[0].value).toBe('hello');
      expect(tokens[1].value).toBe('world');
    });

    it('should skip block comments', () => {
      const result = lex('hello /* this is\na block\ncomment */ world');
      const tokens = result.tokens.filter((t) => t.type !== TokenType.Eof);
      expect(tokens).toHaveLength(2);
      expect(tokens[0].value).toBe('hello');
      expect(tokens[1].value).toBe('world');
    });

    it('should skip hash comments (nginx style)', () => {
      const result = lex('hello # this is a comment\nworld');
      const tokens = result.tokens.filter((t) => t.type !== TokenType.Eof);
      expect(tokens).toHaveLength(2);
      expect(tokens[0].value).toBe('hello');
      expect(tokens[1].value).toBe('world');
    });
  });

  describe('real config snippets', () => {
    it('should tokenize a simple node block', () => {
      const source = `
        node Waveform sine {
          shape sawtooth;
          frequency_hz 0.1;
        }
      `;
      const result = lex(source);
      expect(result.errors).toHaveLength(0);

      const tokens = result.tokens.filter((t) => t.type !== TokenType.Eof);
      expect(tokens.length).toBeGreaterThan(0);

      // The lexer is schema-agnostic: "node" is just an identifier.
      const nodeWords = tokens.filter((t) => t.type === TokenType.Identifier && t.value === 'node');
      expect(nodeWords).toHaveLength(1);
    });

    it('should tokenize connect directive', () => {
      const source = 'connect upstream.rgb[0:3] input[0:3];';
      const result = lex(source);
      expect(result.errors).toHaveLength(0);
    });
  });

  describe('error handling', () => {
    it('should report unterminated string', () => {
      const result = lex('"unterminated');
      expect(result.errors.length).toBeGreaterThan(0);
      expect(result.errors[0].message).toContain('Unterminated');
    });
  });
});
