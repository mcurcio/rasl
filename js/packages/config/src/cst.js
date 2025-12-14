/**
 * Concrete Syntax Tree types for config files.
 *
 * The CST preserves all source information including whitespace and comments,
 * enabling lossless round-tripping and precise error reporting.
 */
/**
 * CST node kinds.
 */
export const CstNodeKind = {
    Document: 'document',
    Directive: 'directive',
    Trivia: 'trivia',
};
/**
 * Serialize a CST back to source text (round-trip).
 */
export function serializeCst(node) {
    // TODO: Implement full serialization
    void node;
    return '';
}
//# sourceMappingURL=cst.js.map