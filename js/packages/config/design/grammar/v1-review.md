# v1 review: grammar system design

**Verdict: FAIL (wrong premise).** The soundness argument holds. The tooling premise does not:
v1 made the Lezer file both the normative grammar and the oracle (the reference that judges the
hand-written parser), and Lezer cannot express v1's lexical rules. Several choices that belong
to the owner were also hidden as "recommended as shown".

Probes: `experiments/v1-review/`.

## What survived

- Longest match over pairwise-disjoint token kinds, plus a syntactic grammar with no LR(1)
  conflicts, gives one parse per input string.
- v1's EBNF, encoded literally in Lezer (`draft.grammar`), generates with no conflicts.
  `a\n{\n}` and `x [1 2]` are rejected.
- interegular: "12 token kinds, 66 pairs, 0 overlapping".
- The stated reason for dropping ANTLR is accurate: ANTLR resolves ambiguity while parsing and
  never reports it.

## Findings

| # | Severity | Finding |
|---|---|---|
| F1 | critical | Lezer's `@precedence` sets which token wins by rule order; it is not longest match. With the order reversed (`g2rev.grammar`), `x //c` lexes as two words. The BadSlice error token cannot be encoded: placed above Word, it makes `a[0:3]` an error; placed below, `a[1]` is accepted; with no precedence the generator refuses to build (`bsHi`, `bsLo`, `bsNone`). Lark's lexer takes the first match, not the longest. |
| F2 | high | The draft EBNF, the Lezer file and the Lark file describe three different languages. Lezer `good2` has no single-quoted strings and no error tokens, and accepts control characters and `include /*.conf`. Nothing ties the checked file to the grammar the spec states. |
| F3 | high | Lezer features can silence conflicts (`!prec`, `~ambig`, `@specialize`, external tokenizers), and nothing forbids them. |
| F4 | high | The owner asked for "a formal EBNF". Lezer notation is not EBNF, and its meaning comes from one implementation. |
| F5 | high | A hidden owner choice: whether tokens may touch with no space between them. `x a [0:3]` is a word plus a list, so one space changes the meaning with no warning. `x "a"[0:3]`, `"a""b"`, `a"b"`, `[a][b]` and `a[0:3]b` are all accepted as separate values. |
| F6 | medium | `a /*\n*/ b` parses as one directive. ECMAScript and Go treat a comment that spans a line break as a line break. |
| F7 | medium | Bare words and comment syntax interact: under nginx-style words, `include /*.conf` opens an unterminated comment, and `//cdn.host/x` starts a comment. |
| F8 | medium | Putting the slice inside the Word token contradicts `rasl-9ze`'s confirmed design ("Bracket expressions stay separate tokens in the CST"), and gives the slice rule two homes. |
| F9 | medium | The value rules (numbers, booleans, string decoding) are not in the conformance corpus. JS and Python parse numbers differently: for `1_000`, JS gives NaN and Python gives 1000.0. |
| F10 | medium | Naming CST node kinds after grammar rules makes the grammar's internal factoring normative (LastDirective versus Directive). |
| F11 | medium | v1 compared two designs without weighing a parser generated from the normative grammar. The oracle must emit the normative tokens and tree; otherwise the TS parser ends up grading itself. |
| F12 | low | Behaviour changes not surfaced: an invalid escape goes from warning to error, a lone CR becomes an error, `a#b` changes meaning, and informative-only recovery conflicts with `rasl-bzv.1`. |
| F13 | low | The input alphabet is undefined: NBSP, BOM, and lone surrogates (which Python cannot hold). |

## What must change (carried into v2)

- One normative grammar, in plain notation whose meaning is the spec's: longest-match regular
  token definitions plus EBNF syntactic rules.
- Every check runs on that file, with no features that silence a check.
- The oracle implements the same lexical rules.
- Slices are reconciled with `rasl-9ze`, or the reversal is raised.
- The value rules enter the corpus.
- F5, F6 and F7 go to the owner.
