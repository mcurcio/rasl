# Config grammar: design record (system layer)

The answer page holds the full discussion:
https://claude.ai/artifact/H64AiZ7yuHTkzod9WauPLf (rounds 1 and 2). This file is the short
durable record. Every choice below is current and can be revised.

## Requirements

| # | Requirement | Source |
|---|---|---|
| R1 | "I want a formal language spec, but I don't care if it's EBNF. I'm ok with some other/better spec variant" (refines 2026-10-21: "I think we need a formal EBNF that describes the language so that we can prove its sound") | owner, 2026-10-22 |
| R1b | "I'm still hopeful we can build on some existing parser generator or code generator so that we can simplify the cross-language support." | owner, 2026-10-22 |
| R2 | Sound = "Both": (a) the grammar is unambiguous, checked by a tool; (b) the parser accepts exactly the grammar's language | owner, 2026-10-21 |
| R3 | "An EBNF gives a language independent syntax. And then parsers can be written against it, and then finally language-specific idiomatic sugar APIs can be layered on top" | owner, 2026-10-21 |
| R4 | "the TS *config* is canonical. The python version of the full runtime is still more comprehensive" | owner, 2026-10-21 |
| R5 | Slices `[n:m]`, `[n:]` and `[:m]`; `[:]` is rejected with a located error | `rasl-9ze.1` |
| R6 | "A is ideal if we don't sacrifice the CST. Otherwise, C." (the condition on choosing ANTLR4) | owner, 2026-10-22 |

## Owner answers

| Question | Answer | Recorded in |
|---|---|---|
| Comments, and `:` in words | B: `#` only, where a token starts. A word that starts with a digit or `-` cannot contain `:` | `rasl-m8w.1` |
| Values touching | A: values are separated by a space or comment; a slice touches its word; punctuation may touch | `rasl-9ze` |
| Which tool | A: ANTLR4, provided the CST is kept. The check below says it is | `rasl-k2e` |

## Current choices

- **The spec.**
  - [Rasl.g4](Rasl.g4) is the one grammar file.
  - Whitespace, comments and newlines are ordinary grammar tokens: nothing goes on a hidden
    channel and nothing is skipped.
  - Lists and value runs are written as loops, not recursion.
  - `*` and `?` are word characters, so include globs work (`rasl-trv`).
  - [config.ebnf](config.ebnf) stays as the readable EBNF view and the reference used in
    testing.
- **Soundness (a), proven in CI:**
  - `g4bison.py` translates the parser rules mechanically, and Bison must report 0 conflicts
    with `%expect 0`.
  - `g4overlap.py` proves that no two token kinds can match the same text.
  - Both checks fail on the planted grammars.
  - The translator refuses predicates, actions, lexer modes and other features that could hide
    a conflict.
- **Soundness (b):** ANTLR4 generates both the TS and the Python parser from that file. On
  14,900 inputs:
  - the TS and Python trees and diagnostics are byte-identical;
  - they match the `config.ebnf` reference parser;
  - there were 0 round-trip failures.
- **The CST**, the condition in R6:
  - It is lossless: every character is in exactly one token, for valid and broken input alike.
  - Node kinds: document, directive, block, list, slice, error.
  - The parts of a slice stay separate tokens.
- **Recovery:**
  - A custom ANTLR error strategy, about 95 lines per language, meets `rasl-bzv.1`.
  - The first error is reported at the real position.
  - A bad statement becomes one error node, and later siblings are kept.
- **Runtime:** the official `antlr4` 4.13.2 for TS (sync, pure JS, about 36 KB gzip in the
  browser) and `antlr4-python3-runtime` 4.13.2 for Python, both pinned to the generator
  version. The fallback is antlr4ng, if CI should not need Java.

## Design rules (design choices)

1. **One file defines the language.** Every parser and every check comes from `Rasl.g4`.
2. **Every character is in exactly one token, and no two token kinds overlap.** So ANTLR's
   tie-break by rule order never decides anything.
3. **ANTLR stays behind the adapter.** Layers above see only our tokens, CST, stable codes and
   `IValue`.

## Recommended as shown (can be reopened)

- **A nesting depth limit (100) with its own error code.** About 1,000 levels crashes both
  runtimes, as it would a recursive hand-written parser.
- **A bad line becomes one error node,** through a one-line override in each language.
- **Error codes tidied:**
  - E2007 for a bad slice;
  - a new code for `{` on its own line;
  - E2002 and E2005 either emitted or removed;
  - touching values get their own code.
- **`connect foo[1];` stays an error.** The other choice is a fourth slice form meaning a
  single channel; that is the owner's call.

## Bead outline (under `rasl-g7n`)

1. **Spec and CI checks:**
   - `Rasl.g4`, with the generated parsers checked in or generated in CI;
   - `g4bison.py`, `g4overlap.py` and the planted grammars;
   - the conformance corpus with alphabet-edge inputs.
2. **TS parser on ANTLR (the tracer):**
   - `connect hyperhdr_color[144:152];` goes from `Rasl.g4` through the TS adapter to `valueOf`
     and on to the engine;
   - `parseSliceTokens` is deleted;
   - `lexer.ts` and `parser.ts` are replaced.
3. **Recovery and stable codes** (`rasl-bzv.1`), in TS.
4. **Python parser on ANTLR** (`rasl-9pn`): the same corpus, replacing crossplane.
5. **Value rules and typed values** (`rasl-9ze`), then the delegator and definitions
   (`rasl-stq`, `rasl-xlo`).

## NOT RUN

- A `tsc` type-check of the adapters.
- A real browser.
- Bison 3.x.
- Linux CI.
- Python versions other than 3.13.
- Performance on large files.
