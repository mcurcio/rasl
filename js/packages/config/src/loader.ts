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
export function walkDirectives(doc: ICstDocument, visitor: DirectiveVisitor): void {
  const visit = (dir: ICstDirective, parent: ICstDirective | null): void => {
    visitor(dir, parent);
    if (dir.body) {
      for (const child of dir.body) visit(child, dir);
    }
  };

  for (const child of doc.children) visit(child, null);
}

/**
 * Find all directives with the given name anywhere in the document.
 */
export function findDirectives(doc: ICstDocument, name: string): ICstDirective[] {
  const out: ICstDirective[] = [];
  walkDirectives(doc, (dir) => {
    if (dir.name === name) out.push(dir);
  });
  return out;
}
