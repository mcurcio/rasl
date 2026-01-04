# CST round-tripping plan

## Goals
- Preserve every byte of the original source (whitespace, comments, delimiters) in the CST.
- Implement `serializeCst` so consumers can round-trip configs without losing formatting.
- Keep the lexer and parser schema-agnostic so downstream DSL layers only deal with directives.

## Approach
1. **Lexer emits trivia**
   - Add token kinds for whitespace, newline, `//`, and `/* */` comments.
   - Preserve the exact lexeme text (no trimming or escape normalisation) so serialization can reuse it verbatim.
   - Carry precise spans for every trivia token.
2. **Parser retains trivia**
   - Stop filtering trivia before parsing; instead, consume it into `leadingTrivia` and `trailingTrivia` collections attached to each `ICstDirective`.
   - Default `preserveTrivia?: boolean` to `true`; allow consumers to drop trivia for performance.
   - Ensure the document node also keeps trailing trivia after the final directive (needed to reproduce EOF whitespace).
3. **Directive structure**
   - Do not reinterpret literal token values for the CST layer—store raw tokens so they can be re-serialized.
   - Add helpers that expose trimmed/decoded values for AST consumers (so round-tripping does not fight higher-level semantics).
4. **Serializer implementation**
   - Walk the document in source order, concatenating `leadingTrivia`, directive text (name + args + braces/semicolons), nested bodies, and `trailingTrivia`.
   - Verify round-trip fidelity with golden tests (parse → serialize → diff should be empty).
5. **Testing**
   - Add Vitest coverage for trivia-heavy samples (mixed comments, multi-line spacing, inline comments).
   - Include regression tests for oddities such as consecutive blank lines, files ending without newline, etc.

## Open questions
- Do we expose a hook for consumers to mutate trivia (e.g., formatter), or keep it internal for now?
- Should `serializeCst` support selective subtree serialization (might be useful for editors)?
