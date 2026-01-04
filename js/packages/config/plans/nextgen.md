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

## Decision points (choose before hardening)
- **Statement termination**
  - Option A: semicolons are required (nginx-style, simplest cross-language).
  - Option B: newline can terminate statements (requires newline tokens + clearer multi-line rules).
- **Literal model**
  - Do identifiers represent only symbols, or can they also be “bare strings”?
  - Do arrays/maps exist as first-class syntax, or are they a DSL-layer concern?
- **Bracket syntax (`[...]`)**
  - Is it a list literal, a “raw bracket expression token”, or reserved for DSL-specific slicing?
- **String semantics**
  - Raw vs cooked storage, escape rules, and whether round-tripping is a first-class guarantee.
- **Comment styles**
  - Exactly which are supported (`//`, `/* */`, `#`), and whether they’re preserved or discarded.
- **Include semantics**
  - Syntax (`include "path"` vs `include path`), resolution context, cycle handling, and error strategy.

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
- Decide whether to emit trivia tokens (whitespace/comments/newlines) and what “preserve” means.
- Store both:
  - **raw lexeme** (for serialization) and
  - **cooked value** (for consumers), where applicable (strings/numbers).
- Tighten span rules (offsets + line/column) and document whether they’re 0- or 1-based.
- Expand identifier rules intentionally (e.g. hyphens?) or document the minimal set as the spec.

### 3) Parser + CST + serializer (round-tripping)
- Make CST structure match the spec (including statement termination rules).
- Remove consumer-specific shaping from the core parser (e.g. bracket-collapsing), replacing it with:
  - structured CST nodes, or
  - a neutral token stream representation, or
  - an opt-in parse mode.
- Implement `serializeCst` with golden round-trip tests (parse → serialize → byte-identical).
- Add focused parser recovery rules and diagnostic codes (not just strings) for stability across languages.

### 4) Multi-file parsing + include resolution
- Implement `parseAsync` + `includeResolver` (no filesystem I/O in core).
- Specify and enforce cycle/depth handling; surface diagnostics with file identity/path.
- Decide whether the “included document” is:
  - inlined into a single AST/CST, or
  - referenced as a graph of documents (better for tooling).

### 5) DSL-layer ergonomics (kept optional and clearly separated)
- Clarify whether `DirectiveDelegator` is a supported public abstraction or an internal convenience.
- If it’s public, pin down traversal semantics and handler return shapes (avoid implicit “magic”).
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
