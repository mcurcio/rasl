# v3: building on a parser generator

> **Status: under review.** Written after the gate answers of 2026-10-22. Q1 was answered (B);
> on Q3 the owner wrote: "I want a formal language spec, but I don't care if it's EBNF. I'm ok
> with some other/better spec variant" and "I'm still hopeful we can build on some existing
> parser generator or code generator so that we can simplify the cross-language support."
> Experiments: `experiments/v3/`.

## Recommendation: tree-sitter

Under this option:

- One grammar file, `grammar.js` (44 lines), is the formal spec.
- tree-sitter generates one parser from it, and both TS (WebAssembly) and Python (a compiled
  package) run that same parser.

What it gives:

- **Soundness (a) is checked when the grammar is built.**
  - tree-sitter refuses to build a grammar with a conflict.
  - A 20-line lint on the generated `grammar.json` forbids the features that would hide a
    conflict.
  - A 33-line check proves no two token kinds overlap.
- **Soundness (b) holds by construction:** TS and Python run the same generated parser.
- **Error recovery is built in** and met `rasl-bzv.1` on every case tried.

## Same grammar, four tools

Each tool ran on the 5 real `.conf` files, 30 edge cases, and the 14,830 generated inputs from
v2. The baseline is the REx parser.

| Run | Verdict diffs | Tree diffs | Round-trip failures |
|---|---|---|---|
| tree-sitter (wasm, TS) | 0 | 0 | 0 |
| tree-sitter (Python) | 0 | 0 | 0 |
| ANTLR4 (TS and Python) | 0 | 0 | 0 |
| Lark (Python) | 0 | 0 | 0 |
| lark-js | failed to load (last release 2022) | – | – |

## What each tool does with a planted conflict

| Tool | Grammar conflict | Overlapping tokens |
|---|---|---|
| tree-sitter | refuses (exit 1); a declared `conflicts:` hides it, so the lint forbids that | not caught by the tool; `disjoint.py` catches it |
| REx | refuses | refuses |
| ANTLR4 | **builds silently**; ambiguity shows only while parsing a given input | silent |
| Lark | refuses | NOT RUN |

## Error recovery

| Input | tree-sitter | ANTLR (default) | REx |
|---|---|---|---|
| unclosed `[` inside a block | keeps the block, adds a missing `]`, parses the next directive | empties the block | stops |
| stray `]` | one error, then parses the next line | drops the rest | stops |

## Options

| | A. tree-sitter (recommended) | B. ANTLR4 plus a second checker | C. Hand-written parsers checked against `config.ebnf` |
|---|---|---|---|
| (a) unambiguous | tree-sitter + 2 small lints | needs REx or Bison on a second grammar | REx + Bison (done in v2) |
| (b) parser = grammar | by construction | by construction | testing only, per language |
| Recovery | built in, shared | custom strategy written twice | written twice |
| Exact first-error position | no: within the error region | yes | yes |
| Runtime | wasm (TS, browser), native (Python) | pure; about 35 KB gzip in JS | none |
| Main cost | Python packages built per platform; the grammar is JavaScript, not EBNF; one tree-sitter version pinned across languages | two grammar files or a translator; recovery duplicated | the most code; two parsers to keep in step |

REx-generated parsers as the runtime were dropped:

- They have no recovery.
- They have the NUL bug in both languages.
- TS and Python report offsets in different units.

## Findings for the spec

- **`include /*.conf` is rejected by `config.ebnf`.** `*` is not a word character. The
  answer page wrongly said "1 word". Globs need `*` and `?`, or quoting.
- **`rasl-bzv.1`'s "resume next line" cannot work for an unclosed `[`.** Lists may span lines,
  so the error is only detectable at `}` or the end of the file.
- **tree-sitter strips a leading BOM.** The adapter has to re-add it as a token.
- **The TS (web) and Python tree-sitter runtimes differed on 42 of 14,830 error positions.**
  The cause is the core version and the input encoding, so both languages must pin one
  version and one encoding.

## NOT RUN

- The Node native tree-sitter addon.
- A browser bundle.
- Python package builds for Linux.
- Performance.
- ANTLR custom recovery.
- Exact error positions derived from tree-sitter.
