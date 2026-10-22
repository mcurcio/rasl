# Next-gen generic config system plan

## Goals

- Make `@rasl/config` a **domain-agnostic** parsing toolkit (no node-graph or RASL-specific semantics in core).
- Publish a **stable, language-spec’d** config language that can be implemented in TS now and ported later (Python/C++).
- Provide **production-ready ergonomics**: clear diagnostics, deterministic behavior, and (optionally) lossless round-tripping.

## Current gaps (from the existing package)

- **RASL leakage in surface area**: package description/README/tests/JSDoc are RASL-centric even though the core parser is mostly directive-generic.
- **Docs don’t match implementation**: parsing API and include semantics must match the implementation; semicolon/newline rules should be specified.
- **Parsing drops information**: lexer/parser currently filter or reshape tokens (blocking byte-identical round-tripping).
- **Grammar edge-cases are accidental**: newline is currently treated as ignorable trivia (so “optional semicolons” can’t work).
- **Tokenization mismatches nginx expectations**: `.` is currently tokenized as punctuation instead of being part of a “word”.
- **Not cross-language-ready**: handwritten parser has no shared grammar artifact for other bindings.

## Current decisions (confirmed)

- **Statement termination**: newline terminates directives; semicolons are optional but required to put multiple directives on one line.
- **No backslash line continuation**: directive headers do not use `\\` escapes.
- **Multi-line bracket lists**: newlines are allowed within `[...]` list literals and do not terminate directives until the matching `]`.
- **Slices are postfix**: slice/range syntax is written without whitespace as `foo[0:3]`.
- **Blocks**: `{` must be on the same line as the directive header it opens.
- **Strings**: support both `'` and `"` quotes.
- **String escapes (v1)**: keep `\\`, `\n`, `\t`, `\r`, `\"`, `\'`.
- **Round-tripping**: byte-identical `serializeCst(parse(x)) === x` is a first-class goal.
- **Comments**: support `//` and `/* */` only.
- **Trivia**: preserve trivia in CST by default.
- **CST storage model**: tokenize everything; the canonical CST storage is the full token stream (including whitespace/comments/newlines).
- **AST facade**: provide a directive-level AST facade on top of the CST; “don’t care about round-trip” consumers use AST; precision consumers can edit CST/tokens directly.
- **`include`**: core feature; include resolution produces a **document graph** (not a single inlined document).
- **`include` paths**: must be quoted string literals; resolver may treat them as globs.
- **Dots**: follow nginx practice (dot is part of a “word”, not a punctuation token).
- **Word charset**: unquoted “words” use only letters/digits/underscores/dots (no hyphens).
- **Include glob ordering**: core sorts glob matches by `resolvedPath` ascending (lexicographic).
- **Diagnostics**: 0-based line/column; stable diagnostic codes + human-readable messages.
- **Public API**: keep the directive-level AST (`ast-directives`); no RASL node/connection AST in this package.
- **Delegation**: `DirectiveDelegator` is intended as a public hook for implementors (notably for `include` processing), and should be strongly typed (avoid `unknown`/`any`).
- **Parser generator**: adopt ANTLR4 and treat the `.g4` grammar as the shared foundation for multi-language bindings.

## Remaining decisions (need confirmation)

- **String escapes (optional v2+)**: decide whether to add common `\uXXXX`/`\xNN` style escapes, or rely on raw UTF-8 source.
  - If added, decide how they interact with byte-identical round-trip (raw lexeme must win).
- **Slice details**: confirm whether `[start:]` is allowed (recommended) and whether `[:end]` / `[:]` are allowed (currently unspecified).

## Units of work (milestones)

### 0) De-RASL-ify the core package surface

- Rewrite `README.md` to describe a generic directive config language (move RASL examples to the RASL consumer package).
- Remove/move any RASL-shaped types that aren’t part of the generic directive layer (e.g. node/connection AST types).
- Replace RASL-centric test fixtures with neutral examples (e.g. `server { listen 8080; }`).

### 1) Write a real language spec + conformance corpus

- Add an explicit grammar (EBNF) + lexical spec (identifier chars, numbers, strings, whitespace, comments).
- Define a versioned “core profile” (minimal features every implementation must support).
- Create a conformance corpus: sample inputs + expected tokens/CST/diagnostics as JSON fixtures.

### 2) ANTLR4 grammar + token model foundation

- Add an ANTLR4 grammar (`.g4`) and treat it as the source of truth for parsing across languages.
- Configure lexer rules so:
  - all tokens keep exact `text` (raw lexeme) for serialization, and
  - whitespace/comments can be on a hidden channel but remain accessible for round-tripping.
- Make newline a structural token (needed for newline-terminated directives).
- Align “word” tokenization with nginx expectations (dots are part of words).
- Define how bracket expressions are tokenized/parsed (list + slice forms).

### 3) Parser + CST + serializer (round-tripping)

- Make CST structure match the spec (newline termination + optional semicolons).
- Make the full token stream the canonical storage, and build directive CST nodes that reference token ranges.
- Remove consumer-specific shaping from parsing (e.g. bracket-collapsing into a string token).
- Implement `serializeCst` with golden round-trip tests (parse → serialize → byte-identical).
- Add focused parser recovery rules and diagnostic codes (not just strings) for stability across languages.

### 4) Multi-file parsing + include resolution

- Implement async `parse` + required `loader` (no filesystem I/O in core).
- Specify and enforce cycle/depth handling; surface diagnostics with file identity/path.
- Use a document graph representation so included files can be round-tripped back to their original sources.
- Support glob expansion in the resolver surface and define deterministic match ordering.

### 5) Consumer APIs (three tiers)

- **Power users**: token-level + CST editing with byte-identical serialization.
- **Most consumers**: directive-level AST facade (`ast-directives`) over CST for easy traversal/editing.
- **Minimal integration**: a higher-level registration API (TBD) that lets consumers register directive handlers and have them invoked automatically (built on `DirectiveDelegator`).

### 6) Tooling (optional, but “production-ready” usually wants it)

- CLI: parse/validate/format/print (`--tokens`, `--cst`, `--ast`, `--json`, `--diagnostics`).
- Formatter: deterministic output, optionally with trivia-preservation modes.
- Editor support: syntax highlighting + (later) LSP features backed by CST spans.

### 7) Cross-language readiness (Python/C++ roadmap enablers)

- Treat the spec + conformance corpus as the source of truth.
- Define a canonical, language-agnostic JSON form for CST/diagnostics to validate other implementations.
- Publish a small “porting guide” with pitfalls (string escapes, newline rules, error recovery expectations).

### 8) Release hardening and sustainability

- Adopt semver discipline for the spec and the library API.
- Add fuzz/property tests for the lexer/parser (crash-free, linear-time behavior).
- Document security posture (no I/O by default; include resolution is caller-provided).
- Add benchmarks + performance budgets for large files.

## Related plans

- `plans/roundtrip.md` (trivia + serialization)
- `plans/include.md` (include resolver + async parsing)
- `plans/scope.md` (directive delegation / scoping helpers)
