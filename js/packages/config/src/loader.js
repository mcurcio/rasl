/**
 * CST utilities for traversing parsed config files.
 */
/**
 * Walk all directives in a document depth-first.
 */
export function walkDirectives(doc, visitor) {
    const visit = (dir, parent) => {
        visitor(dir, parent);
        if (dir.body) {
            for (const child of dir.body)
                visit(child, dir);
        }
    };
    for (const child of doc.children)
        visit(child, null);
}
/**
 * Find all directives with the given name anywhere in the document.
 */
export function findDirectives(doc, name) {
    const out = [];
    walkDirectives(doc, (dir) => {
        if (dir.name === name)
            out.push(dir);
    });
    return out;
}
//# sourceMappingURL=loader.js.map