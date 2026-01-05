/**
 * Tests for the config lexer.
 */

import { describe, expect, it } from "vitest";

import { lex } from "./lexer.js";
import { DiagnosticCode, TokenType } from "./tokens.js";

describe("Lexer", () => {
  describe("basic tokens", () => {
    it("should tokenize words (identifiers with dots)", () => {
      const result = lex("hello world server.name foo.bar.baz");
      const words = result.tokens.filter((t) => t.type === TokenType.Word);
      expect(words).toHaveLength(4);
      expect(words[0].text).toBe("hello");
      expect(words[1].text).toBe("world");
      expect(words[2].text).toBe("server.name");
      expect(words[3].text).toBe("foo.bar.baz");
    });

    it("should tokenize numbers", () => {
      const result = lex("42 3.14 -5 1e10 -2.5e-3");
      const numbers = result.tokens.filter((t) => t.type === TokenType.Number);
      expect(numbers).toHaveLength(5);
      expect(numbers[0].value).toBe(42);
      expect(numbers[1].value).toBe(3.14);
      expect(numbers[2].value).toBe(-5);
      expect(numbers[3].value).toBe(1e10);
      expect(numbers[4].value).toBe(-2.5e-3);
    });

    it("should tokenize strings with both quote styles", () => {
      const result = lex("\"hello\" 'world'");
      const strings = result.tokens.filter((t) => t.type === TokenType.String);
      expect(strings).toHaveLength(2);
      expect(strings[0].text).toBe('"hello"');
      expect(strings[0].value).toBe("hello");
      expect(strings[1].text).toBe("'world'");
      expect(strings[1].value).toBe("world");
    });

    it("should handle string escapes", () => {
      const result = lex('"line1\\nline2\\ttab\\r\\n"');
      const strings = result.tokens.filter((t) => t.type === TokenType.String);
      expect(strings).toHaveLength(1);
      expect(strings[0].value).toBe("line1\nline2\ttab\r\n");
    });

    it("should handle escaped quotes in strings", () => {
      const result = lex('"say \\"hello\\""');
      const strings = result.tokens.filter((t) => t.type === TokenType.String);
      expect(strings).toHaveLength(1);
      expect(strings[0].value).toBe('say "hello"');
    });

    it("should tokenize booleans as words with boolean values", () => {
      const result = lex("true false");
      const words = result.tokens.filter((t) => t.type === TokenType.Word);
      expect(words).toHaveLength(2);
      expect(words[0].text).toBe("true");
      expect(words[0].value).toBe(true);
      expect(words[1].text).toBe("false");
      expect(words[1].value).toBe(false);
    });

    it("should tokenize punctuation", () => {
      const result = lex("{ } [ ] ; : ,");
      const types = result.tokens
        .filter((t) => t.type !== TokenType.Whitespace && t.type !== TokenType.Eof)
        .map((t) => t.type);
      expect(types).toEqual([
        TokenType.LeftBrace,
        TokenType.RightBrace,
        TokenType.LeftBracket,
        TokenType.RightBracket,
        TokenType.Semicolon,
        TokenType.Colon,
        TokenType.Comma,
      ]);
    });
  });

  describe("trivia preservation", () => {
    it("should preserve whitespace tokens", () => {
      const result = lex("hello   world");
      const ws = result.tokens.filter((t) => t.type === TokenType.Whitespace);
      expect(ws).toHaveLength(1);
      expect(ws[0].text).toBe("   ");
    });

    it("should preserve newline tokens", () => {
      const result = lex("hello\nworld\n\nfoo");
      const newlines = result.tokens.filter((t) => t.type === TokenType.Newline);
      expect(newlines).toHaveLength(3);
    });

    it("should preserve line comments with //", () => {
      const result = lex("hello // this is a comment\nworld");
      const comments = result.tokens.filter((t) => t.type === TokenType.LineComment);
      expect(comments).toHaveLength(1);
      expect(comments[0].text).toBe("// this is a comment");
    });

    it("should preserve line comments with #", () => {
      const result = lex("hello # this is a comment\nworld");
      const comments = result.tokens.filter((t) => t.type === TokenType.LineComment);
      expect(comments).toHaveLength(1);
      expect(comments[0].text).toBe("# this is a comment");
    });

    it("should preserve block comments", () => {
      const result = lex("hello /* multi\nline */ world");
      const comments = result.tokens.filter((t) => t.type === TokenType.BlockComment);
      expect(comments).toHaveLength(1);
      expect(comments[0].text).toBe("/* multi\nline */");
    });
  });

  describe("round-trip preservation", () => {
    it("should preserve exact source text", () => {
      const source = "server {\n  listen 8080;\n  // comment\n}";
      const result = lex(source);
      const reconstructed = result.tokens.map((t) => t.text).join("");
      expect(reconstructed).toBe(source);
    });

    it("should preserve complex source with all token types", () => {
      const source = `
server {
  listen 8080;
  server.name "example.com";
  enabled true;
  /* block
     comment */
  timeout 30.5;
}
`;
      const result = lex(source);
      const reconstructed = result.tokens.map((t) => t.text).join("");
      expect(reconstructed).toBe(source);
    });

    it("should preserve whitespace variations", () => {
      const source = "a\t\tb   c\r\nd";
      const result = lex(source);
      const reconstructed = result.tokens.map((t) => t.text).join("");
      expect(reconstructed).toBe(source);
    });
  });

  describe("source locations", () => {
    it("should track 0-based line and column", () => {
      const result = lex("hello\nworld");
      const words = result.tokens.filter((t) => t.type === TokenType.Word);
      expect(words[0].span.start.line).toBe(0);
      expect(words[0].span.start.column).toBe(0);
      expect(words[1].span.start.line).toBe(1);
      expect(words[1].span.start.column).toBe(0);
    });

    it("should track byte offsets", () => {
      const result = lex("ab cd");
      const words = result.tokens.filter((t) => t.type === TokenType.Word);
      expect(words[0].span.start.offset).toBe(0);
      expect(words[0].span.end.offset).toBe(2);
      expect(words[1].span.start.offset).toBe(3);
      expect(words[1].span.end.offset).toBe(5);
    });
  });

  describe("error handling", () => {
    it("should report unterminated string", () => {
      const result = lex('"unterminated');
      expect(result.errors).toHaveLength(1);
      expect(result.errors[0].code).toBe(DiagnosticCode.UnterminatedString);
    });

    it("should report unterminated block comment", () => {
      const result = lex("/* unterminated");
      expect(result.errors).toHaveLength(1);
      expect(result.errors[0].code).toBe(DiagnosticCode.UnterminatedBlockComment);
    });

    it("should report unexpected characters", () => {
      const result = lex("hello @ world");
      expect(result.errors).toHaveLength(1);
      expect(result.errors[0].code).toBe(DiagnosticCode.UnexpectedCharacter);
    });

    it("should continue lexing after errors", () => {
      const result = lex('"unterminated\nhello');
      const words = result.tokens.filter((t) => t.type === TokenType.Word);
      expect(words).toHaveLength(1);
      expect(words[0].text).toBe("hello");
    });
  });

  describe("nginx-style compatibility", () => {
    it("should handle dotted identifiers as single words", () => {
      const result = lex("proxy_pass http.upstream.backend");
      const words = result.tokens.filter((t) => t.type === TokenType.Word);
      expect(words).toHaveLength(2);
      expect(words[0].text).toBe("proxy_pass");
      expect(words[1].text).toBe("http.upstream.backend");
    });

    it("should handle typical nginx directive", () => {
      const source = "server_name example.com www.example.com;";
      const result = lex(source);
      expect(result.errors).toHaveLength(0);
      const words = result.tokens.filter((t) => t.type === TokenType.Word);
      expect(words).toHaveLength(3);
    });
  });
});
