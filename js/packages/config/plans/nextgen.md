# Next-gen generic config system plan

## Goals
- Make `@rasl/config` a **domain-agnostic** parsing toolkit (no node-graph or RASL-specific semantics in core).
- Publish a **stable, language-spec’d** config language that can be implemented in TS now and ported later (Python/C++).
- Provide **production-ready ergonomics**: clear diagnostics, deterministic behavior, and (optionally) lossless round-tripping.

## Current gaps (from the existing package)
- **RASL leakage in surface area**: package description/README/tests/JSDoc are RASL-centric even though the core parser is mostly directive-generic.
- **Docs don’t match implementation**: `parseAsync`, `include`, and `serializeCst` are described but not implemented; semicolon/newline rules are underspecified.
- **Grammar edge-cases are accidental**: newline is currently just whitespace (so “optional semicolons” can’t work without a newline token model).
- **Ad-hoc token shaping**: bracketed forms (`[...]`) are collapsed into a string token today, which bakes in one consumer’s expectations.

## Current decisions (confirmed)
- **Statement termination**: newline terminates directives; semicolons are optional but required to put multiple directives on one line.
- **Multi-line directives**: args may span multiple lines only via an explicit “newline escape” mechanism (TBD: exact syntax).
- **Strings**: support both `'` and `"` quotes.
- **String escapes (v1)**: keep `\\`, `\n`, `\t`, `\r`, `\"`, `\'`.
- **Round-tripping**: byte-identical `serializeCst(parse(x)) === x` is a first-class goal.
- **Comments**: support `//` and `/* */` only.
- **Trivia**: preserve trivia in CST by default.
- **`include`**: core feature; include resolution produces a **document graph** (not a single inlined document).
- **Identifiers**: underscores only (no hyphens) and allow `.` inside identifiers.
- **Diagnostics**: 0-based line/column; stable diagnostic codes + human-readable messages.
- **Public API**: keep the directive-level AST (`ast-directives`); no RASL node/connection AST in this package.
- **Delegation**: `DirectiveDelegator` is intended as a public hook for implementors (notably for `include` processing).

## Remaining decisions (need confirmation)
- **Newline escape syntax**: recommended is trailing backslash before newline (with a clear rule about whether trailing spaces/comments are allowed).
- **Bracket syntax (`[...]`)**: recommendation for cross-language + RASL-compat is to support both:
  - list literal: `[a, b, c]`
  - slice/range literal: `[start:end]` (also allow `[:end]`, `[start:]`, `[:]`)
  while keeping round-trip via raw tokens/lexemes.
- **String escapes (optional v2+)**: decide whether to add common `\uXXXX`/`\xNN` style escapes, or rely on raw UTF-8 source.
- **`include` surface syntax**: recommend requiring a string literal path (covers relative + absolute paths cleanly).

## Units of work (milestones)

### 0) De-RASL-ify the core package surface
- Rewrite `README.md` to describe a generic directive config language (move RASL examples to the RASL consumer package).
- Remove/move any RASL-shaped types that aren’t part of the generic directive layer (e.g. node/connection AST types).
- Replace RASL-centric test fixtures with neutral examples (e.g. `server { listen 8080; }`).

### 1) Write a real language spec + conformance corpus
- Add an explicit grammar (EBNF) + lexical spec (identifier chars, numbers, strings, whitespace, comments).
- Define a versioned “core profile” (minimal features every implementation must support).
- Create a conformance corpus: sample inputs + expected tokens/CST/diagnostics as JSON fixtures.

### 2) Token model + lexer hardening
- Emit trivia tokens (whitespace/comments/newlines) and define “preserve” precisely (default: preserve).
- Store both:
  - **raw lexeme** (for serialization) and
  - **cooked value** (for consumers), where applicable (strings/numbers).
- Tighten span rules (offsets + 0-based line/column) and document it in the spec.
- Lock identifier rules: `[A-Za-z_][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)*` (no hyphens).

### 3) Parser + CST + serializer (round-tripping)
- Make CST structure match the spec (newline termination + newline-escape continuation).
- Remove consumer-specific shaping from the core parser (e.g. bracket-collapsing), replacing it with:
  - structured CST nodes, or
  - a neutral token stream representation, or
  - an opt-in parse mode.
- Implement `serializeCst` with golden round-trip tests (parse → serialize → byte-identical).
- Add focused parser recovery rules and diagnostic codes (not just strings) for stability across languages.

### 4) Multi-file parsing + include resolution
- Implement `parseAsync` + `includeResolver` (no filesystem I/O in core).
- Specify and enforce cycle/depth handling; surface diagnostics with file identity/path.
- Use a document graph representation so included files can be round-tripped back to their original sources.

### 5) DSL-layer ergonomics (kept optional and clearly separated)
- Treat `DirectiveDelegator` as a supported public abstraction and pin down traversal semantics + handler return shapes (avoid implicit “magic”).
- Keep RASL-specific helpers out of the core; build them in a dedicated consumer package.

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
