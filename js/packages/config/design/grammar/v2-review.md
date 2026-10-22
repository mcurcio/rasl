# v2 review: grammar system design

**Verdict: FAIL on the evidence; the grammar itself held.** Every probe below was re-run by the
reviewer. The answer page ([gate.html](gate.html)) states the corrected claims: R2(b) is
*tested*, not proven, and the gaps below are part of the first build step.

## What held

- The LALR(1) proof runs on `config.ebnf` itself. Regenerating the Bison translation gives the
  same `config.y`, and Bison reports 0 conflicts.
- REx's lexical-ambiguity check matches pairwise token disjointness under longest match. Three
  planted overlaps were each caught.
- Whitespace and comment placement behaves on every edge case tried: trailing comments,
  comments in lists, a BOM, `x a [0:3]`, `a[ 0:3]`, `[:]`, a lone CR.
- REx's per-state lexer yields the same tokens as the spec's lexer for the current token set.
- All 5 repo `.conf` files are valid; their non-ASCII characters sit only in comments.
- REx: Apache-2.0, last push 2026-10-21, release v6.2 (2026-05-30), one maintainer.

## Findings

| # | Severity | Finding | Where it went |
|---|---|---|---|
| F1 | high | The test parser treats NUL as end of input. It accepts `x a\u0000}}}garbage` with no error, and its tokens do not round-trip. The corpus has no NUL, controls, emoji or lone surrogates | First build step |
| F2 | high | The lexer has no independent check: the differential test feeds Bison the test parser's own tokens. REx's context-independent lexer mode has a reproduced bug; the vendored build is an unreleased snapshot | First build step: pin a released REx, report the bug upstream |
| F3 | high | "One file" overstated: first-error selection lives in `oracle.ts`, and the `error` node kind and recovery rules are not in `config.ebnf` | First build step: write them into the spec |
| F4 | high | R2(b) was called proven; it is tested, and the TS parser has not run | Page corrected |
| F5 | high | Shipping generated parsers was not weighed properly | Page: shape A vs B table under Q3 |
| F6 | medium | Digit-led words cannot hold `:`, so `server 127.0.0.1:3000;` (a `parser.test.ts` fixture), MAC addresses and `10:30` break | Page: Q1 |
| F7 | medium | The token-boundary check covers accepted inputs only | First build step |
| F8 | medium | The alphabet row said strings may hold any character; the grammar excludes controls and DEL | Page corrected |
| F9 | medium | Code-point offsets not argued against UTF-16 units or UTF-8 bytes | Page: listed as a recommended-as-shown cost |
| F10 | low | The planted-bad grammars come from an older draft; one fails for a syntax reason | First build step: rebuild from the current file |
| F11 | low | The token alphabet is listed three times by hand | Code architects |
| F12 | low | The file uses REx layout (`<?TOKENS?>`, `$`) beyond plain XML §6 EBNF | Stated on the page |
