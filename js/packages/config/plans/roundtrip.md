# CST round-tripping plan

## Goals

- Preserve every byte of the original source (whitespace, comments, delimiters) via a full-fidelity token stream.
- Implement `serializeCst` so `serializeCst(parse(x).cst) === x` (byte-identical) by default.
- Keep the directive model schema-agnostic so downstream DSL layers only deal with directives.

## Approach

1. **Tokenize everything (canonical storage)**
   - Lexer emits a full token stream including whitespace, newlines, and comments.
   - Each token stores its exact source `text` (raw lexeme) and a precise span (0-based line/column).
   - Comments supported: `//` and `/* */`.
2. **Parser builds directive CST as a view over tokens**
   - The CST document owns the token list.
   - Each directive node stores token-range references (start/end token indices, plus ranges for name/args/body) rather than copying tokens.
   - Consumers can either:
     - edit tokens/ranges directly (max precision), or
     - use an AST facade that rewrites token ranges (simpler, may normalize formatting).
3. **Serialization is token concatenation**
   - `serializeCst` concatenates token `text` in order.
   - For subtree serialization, concatenate tokens in the node’s token range.
4. **Edits are token-splices**
   - Provide utilities for inserting/replacing/removing token ranges while keeping spans stable enough for diagnostics.
   - Avoid “attach trivia to nodes” heuristics as the primary storage; trivia is already in the token stream.
5. **Testing**
   - Golden tests: parse → serialize equals input byte-for-byte.
   - Mutation tests: edit a directive name/arg and assert only the intended token ranges change.

## Open questions

- Do we expose a stable “printer” for AST-level edits, or is token-splicing the only supported way to preserve formatting?
- Should `serializeCst` support selective subtree serialization (useful for editors and patch-based tooling)?
