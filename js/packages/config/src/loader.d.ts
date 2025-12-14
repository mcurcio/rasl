/**
 * CST utilities for traversing parsed config files.
 */
import type { ICstDirective, ICstDocument } from './cst.js';
/**
 * Error during config loading.
 */
export type DirectiveVisitor = (directive: ICstDirective, parent: ICstDirective | null) => void;
/**
 * Walk all directives in a document depth-first.
 */
export declare function walkDirectives(doc: ICstDocument, visitor: DirectiveVisitor): void;
/**
 * Find all directives with the given name anywhere in the document.
 */
export declare function findDirectives(doc: ICstDocument, name: string): ICstDirective[];
//# sourceMappingURL=loader.d.ts.map