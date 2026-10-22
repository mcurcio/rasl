# Config grammar design (work in progress)

Design work for the formal grammar of the `@rasl/config` language and the three layers on top
of it (bead `rasl-g7n`). This folder collects the design as it develops. No parser code changes here.

Owner requirements (2026-10-21):

- "I think we need a formal EBNF that describes the language so that we can prove its sound"
- Sound = "Both": (a) the grammar is unambiguous, so every valid input has exactly one parse,
  checked by a tool; (b) the parser accepts exactly the grammar's language
- "An EBNF gives a language independent syntax. And then parsers can be written against it,
  and then finally language-specific idiomatic sugar APIs can be layered on top"
- "the TS *config* is canonical. The python version of the full runtime is still more
  comprehensive"
- Slice forms `[n:m]`, `[n:]` and `[:m]` are allowed; `[:]` is rejected (`rasl-9ze.1`)

## Contents

| Path | What it is | Status |
|---|---|---|
| [v1-draft.md](v1-draft.md) | First draft: EBNF, where the code and the old rules disagree, soundness plan, layer interfaces | Superseded: failed review |
| [v1-review.md](v1-review.md) | Adversarial review of v1 (verdict: wrong premise) | Done |
| `experiments/v1-draft/` | The v1 grammar written for Lezer, Lark, Bison, ANTLR and an LL(1) check, plus probe scripts run against today's lexer and parser | Evidence for v1 |
| `experiments/v1-review/` | The reviewer's Lezer probes (precedence order, error-token encoding) | Evidence for the review |
| v2 draft | One grammar file in plain EBNF, with every check run on that same file | In progress |
| Answer page | The owner-gate page with at most 3 questions | After v2 |

The experiment scripts were run from a scratch directory outside the repo, so their import
paths and tool installs (npx, uvx) are not wired into this package. They are a record, not a
test suite.
