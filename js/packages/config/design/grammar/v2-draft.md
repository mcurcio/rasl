# v2 draft: one EBNF file, proven sound

> **Status: under review.** This revision replaces [v1-draft.md](v1-draft.md) and answers
> [v1-review.md](v1-review.md). The grammar is [config.ebnf](config.ebnf): this page does not
> repeat it. The owner answers the three questions below on the answer page; this file is the
> record. Every choice here can be revised.

## Conclusions

- **One file is the language.** [config.ebnf](config.ebnf) (70 lines, W3C EBNF from XML 1.0
  §6) holds the token rules, the grammar rules, the value rules and the tree-node names. Every
  check reads that file, or a file a script produces from it.
- **Existing tools do the checking.**
  - [REx](https://github.com/GuntherRademacher/rex-parser-generator) (Apache-2.0) reads W3C
    EBNF. It reports grammar conflicts and overlapping token kinds, its lexer takes the longest
    match, and it generates parsers in TypeScript and Python.
  - Bison checks the same file a second time, through a 70-line mechanical translation.
- **Soundness (a), unambiguity, holds.** REx reports "grammar is LALR(1)" (a standard property:
  a grammar that passes has exactly one parse for every valid input), and Bison reports 0
  conflicts. Both tools reject all 5 deliberately broken grammars, and REx rejects a
  deliberately overlapping token set.
- **Soundness (b), the parser matches the grammar, is proven by testing.** On 14,830 generated
  and mutated inputs, the REx-generated reference parser (the "oracle") and Bison agree on every
  accept/reject verdict and on all 7,847 first-error positions. There were 0 round-trip
  failures, and all 5 repo `.conf` files are valid.
- **v1's open problems are closed as classes:**
  - Slices are separate tokens, keeping `rasl-9ze`.
  - Whether tokens may touch is a stated rule.
  - Numbers are a value rule with one decider.
  - Tree-node kinds are spec concepts.
  - The input alphabet is exact.

## Requirements

| # | Requirement | Source |
|---|---|---|
| R1 | "I think we need a formal EBNF that describes the language so that we can prove its sound" | owner, 2026-10-21 |
| R2 | Sound = "Both": (a) unambiguous, checked by a tool; (b) the parser accepts exactly the grammar's language | owner, 2026-10-21 |
| R3 | "An EBNF gives a language independent syntax. And then parsers can be written against it, and then finally language-specific idiomatic sugar APIs can be layered on top" | owner, 2026-10-21 |
| R4 | "the TS *config* is canonical. The python version of the full runtime is still more comprehensive" | owner, 2026-10-21 |
| R5 | Slices `[n:m]`, `[n:]` and `[:m]` are allowed; `[:]` is rejected with a located diagnostic | `rasl-9ze.1` |
| D1 | Byte-identical round trip | `rasl-m8w` |
| D2 | Diagnostics are 0-based and carry stable codes | `rasl-bzv` |
| D3 | The core does no I/O | `rasl-m8w` |
| D4 | "Bracket expressions stay separate tokens in the CST" | `rasl-9ze` (confirmed) |
| D5 | Recovery keeps the block and its later siblings; one located E2004; parsing resumes on the next line | `rasl-bzv.1` |

## The language as drafted

| Area | Current choice |
|---|---|
| Comments | `#` to end of line, and only where a token starts (Q1) |
| Words | `NameStart NameChar*` or `NumberStart NumberChar*`. `/` is a plain word character. A word that starts with a digit or `-` cannot contain `:`, so `[144:152]` reads as a slice |
| Touching | Two values must be separated by a space or comment. A slice must touch its word. Punctuation may touch anything (Q2) |
| Slices | A word touching `[n:m]`, `[n:]` or `[:m]`, as separate tokens. `[:]` and non-integer bounds give E2007 |
| Numbers | A word whose whole text is a JSON number (RFC 8259). JS and Python read exactly this set the same way |
| Escapes | `\\ \" \' \n \t \r`. Any other escape is error E1004 (it was warning W1004), so `\u` can be added later without changing what any file means |
| Alphabet | Strings and comments may hold any character except a lone surrogate. Elsewhere only ASCII token characters are allowed; anything else is BadChar (E1003). A BOM is allowed only first |
| Offsets | Code points, 0-based |
| Tree nodes | `document`, `directive`, `block`, `list`, `slice`, `error`. How the grammar is factored never shows in the tree |
| Recovery | The first diagnostic is normative. Four recovery rules, each covered by a reviewed corpus case |

## Questions for the owner

1. **Q1. Comment syntax, given that `/` is a word character.**
   - Recommended: `#` only.
   - Alternatives: `//` and `/* */` only, as the plan says; or all three, as today.
   - All three today means `include /*.conf` opens an unterminated comment.
2. **Q2. Must values be separated, as a rule for the whole language?**
   - Recommended: yes; a slice must touch its word.
   - Alternatives: only slices must touch; or allow a space before a slice.
3. **Q3. Drop ANTLR4 for the EBNF file?** The plan marked "adopt ANTLR4" as confirmed.
   - Recommended: drop ANTLR4; REx and Bison check the file; hand-written parsers are judged
     against the oracle.
   - Alternatives: ship REx-generated parsers at run time; or keep ANTLR4.

## Soundness evidence

| Property | Check | Output |
|---|---|---|
| (a) unambiguous | `rex -lalr 1 config.ebnf` | `grammar is LALR(1)`, exit 0 |
| (a) second tool | `ebnf2bison.py`, then `bison` with `%expect 0` | 0 conflicts |
| (a) the checks catch errors | 5 planted-bad grammars (`experiments/v2/g/bad/`) | REx and Bison exit 1 on all 5 |
| tokens never overlap | `derive-tokens.sh` builds a scanner over the 15 token kinds | no overlaps; a planted overlap is caught |
| longest match | a short rule listed before a long one | `//c /` lexes long-first |
| (b) parser = grammar | `gen.py` inputs plus mutations; REx oracle against Bison | 14,830 inputs; 0 disagreements; 0 round-trip failures |
| real files | the oracle on the 5 repo `.conf` files | all valid |
| (b) TS parser | the same corpus in CI | NOT RUN: the parser is not rebuilt yet |

Caveats:

- The grammar is LALR(1) but not LL(1). A directive may omit its terminator only before `}` or
  end of input, so a top-down parser has to read the whole header first.
- A REx bug: LALR combined with `-contextindependentlexer` fails when the start rule begins
  with an optional token (repro: `experiments/v2/bisect/t3.ebnf`). The oracle therefore uses
  REx's per-state lexer, and asserts that its token boundaries match the normative token
  stream on every accepted input.

## Three layers

1. **Layer 1, the spec:**
   - `config.ebnf`;
   - a conformance corpus of JSON cases, one per input: tokens, tree, first diagnostic, plus
     reviewed recovery fixtures;
   - the corpus is emitted by the oracle, which runs only in tests.
2. **Layer 2, the TS parser:**
   - `parseDocument(source)` returns the tokens, the tree and the diagnostics.
   - `valueOf()` is the one place that decides word, number, boolean, string, slice or list.
   - Tokens keep their raw text, with no decoded `value` field.
3. **Layer 3, TS sugar:**
   - the AST facade, `values: IValue[]` (replacing `args` and `argValues`);
   - `DirectiveDelegator` (`rasl-stq`);
   - declarative definitions (`rasl-xlo`).

   These read `IValue` and never re-parse text.

The Python port gets `config.ebnf` and the corpus as its acceptance test.

## Costs

- An external C++ tool in CI (REx, about 25 s to build), with a single maintainer.
- About 440 lines of in-repo scripts.
- Breaking changes, with no shims:
  - the Number token is removed;
  - `token.value` is removed;
  - offsets move from UTF-16 units to code points;
  - W1004 becomes an error.
- The recovery fixtures are reviewed by hand.

## NOT RUN / NOT VERIFIED (as reported by the design agent)

- **NOT RUN:**
  - the TS runtime parser against the corpus;
  - the Python port;
  - a second token-overlap tool;
  - REx on Linux CI;
  - the recovery fixtures.
- **NOT VERIFIED:** code-point offsets for characters outside the Basic Multilingual Plane
  (emoji and similar).
