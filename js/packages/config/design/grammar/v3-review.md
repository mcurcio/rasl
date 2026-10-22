# v3 review: the tree-sitter recommendation

**Verdict: FAIL (wrong premise).** The recommendation held that tree-sitter simplifies
cross-language support. The data in its own experiments ranks ANTLR4 above it. The answer
page (round 2) now recommends ANTLR4 and puts the choice to the owner.

## Findings

| # | Severity | Finding |
|---|---|---|
| F1 | critical | Output identical to the REx reference, out of 14,830 inputs: ANTLR4 TS 14,830 and Python 14,830; tree-sitter web 11,904 and Python 11,785. ANTLR4 runs pure JS and pure Python with a sync API, and its `.g4` follows `config.ebnf` almost line for line. Both tools need a second checker, so that does not separate them. |
| F2 | high | With the recommended versions, tree-sitter's TS and Python runtimes differ on 142 lines (124 error offsets). Even with versions matched, 42 still differ; the cause is input encoding. Each upgrade changes the diagnostics (82 offsets between web 0.26 and 0.27). |
| F3 | high | The diagnostics break on the recommendation's own probes. `{` on its own line is rejected with zero diagnostics. `x a"b"`, `x 127.0.0.1:3000` and `x a[:]` are labelled as a stray `]`. A broken list swallows the next sibling directive. |
| F4 | high | The first error points too early in 1,726 of 7,847 rejected inputs. The real-position requirement was dropped without saying so. |
| F5 | high | web-tree-sitter accepts lone surrogates that the grammar excludes, and Python cannot encode them. The corpus had no such inputs. |
| F6 | medium | `disjoint.py` checks the wrong property: tree-sitter only tries the tokens valid in the current parse state. A planted grammar passed both lints and parses differently from longest match. |
| F7 | medium | tree-sitter silently resolves ambiguity inside repeats (`repeat1(choice('a', seq('a','a')))` builds with exit 0). |
| F8 | medium | `grammar.js` plus runtime behaviour (BOM stripping, per-state lexing, flattening) defines the language, so it is not a language-independent spec. |
| F9 | medium | Untested costs: the async wasm load breaks today's sync `parseDocument` and needs I/O at the edges; no Python wheel was built; the adapter is still written twice. |

## What held

- `generate` refuses conflicts outside repeats and between named rules.
- Whitespace is modelled explicitly, and round trip held in both languages.
- NUL, a double BOM, and a BOM in mid-line are all rejected.
