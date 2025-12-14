/**
 * Concrete Syntax Tree types for config files.
 *
 * The CST preserves all source information including whitespace and comments,
 * enabling lossless round-tripping and precise error reporting.
 */
/**
 * CST node kinds.
 */
export declare const CstNodeKind: {
    readonly Document: "document";
    readonly Directive: "directive";
    readonly Trivia: "trivia";
};
export type CstNodeKind = (typeof CstNodeKind)[keyof typeof CstNodeKind];
/**
 * Source location span.
 */
export interface ISourceSpan {
    start: number;
    end: number;
    line: number;
    column: number;
}
/**
 * Trivia attached to a CST node (for round-tripping).
 */
export interface ICstTrivia {
    leadingTrivia: ICstTriviaItem[];
    trailingTrivia: ICstTriviaItem[];
}
/**
 * A single trivia item (whitespace or comment).
 */
export interface ICstTriviaItem {
    kind: 'whitespace' | 'newline' | 'line_comment' | 'block_comment';
    text: string;
    span: ISourceSpan;
}
/**
 * Base interface for all CST nodes.
 * Includes trivia for lossless round-tripping.
 */
export interface ICstNode {
    kind: CstNodeKind;
    span: ISourceSpan;
    trivia?: ICstTrivia;
}
import type { IToken } from './tokens.js';
/**
 * Root document node.
 */
export interface ICstDocument extends ICstNode {
    kind: typeof CstNodeKind.Document;
    children: ICstDirective[];
}
/**
 * A directive.
 *
 * In nginx-style syntax, both statements and blocks are directives:
 *
 * - Statement: `name arg1 arg2;`
 * - Block: `name arg1 { ... }`
 */
export interface ICstDirective extends ICstNode {
    kind: typeof CstNodeKind.Directive;
    name: string;
    args: IToken[];
    body: ICstDirective[] | null;
}
/**
 * Serialize a CST back to source text (round-trip).
 */
export declare function serializeCst(node: ICstNode): string;
//# sourceMappingURL=cst.d.ts.map