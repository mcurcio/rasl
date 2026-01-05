import type { IAstDirective } from "./ast.js";
import { getDirectiveName } from "./cst.js";
import type { IDocumentGraph, IDocumentNode } from "./graph.js";

/**
 * Iterate directives in include-expanded order.
 *
 * Includes are resolved during parsing and expanded in-place during iteration.
 * This preserves directive ordering and brace scopes; only `include` directives
 * are expanded (and not yielded).
 */
export function* iterateDirectives(graph: IDocumentGraph): Generator<IAstDirective> {
  const expansionStack = new Set<string>();

  function* iterateNode(node: IDocumentNode): Generator<IAstDirective> {
    if (expansionStack.has(node.resolvedPath)) return;
    expansionStack.add(node.resolvedPath);

    function* iterateList(list: Iterable<IAstDirective>): Generator<IAstDirective> {
      for (const directive of list) {
        const name = getDirectiveName(node.parseResult.cst, directive.cst);
        if (name === "include") {
          const edge = node.includes.get(directive.cst);
          const targets = edge?.targets ?? [];
          for (const target of targets) yield* iterateNode(target);
          continue;
        }

        yield directive;

        if (directive.body) {
          yield* iterateList(directive.body);
        }
      }
    }

    yield* iterateList(node.ast.children);
    expansionStack.delete(node.resolvedPath);
  }

  yield* iterateNode(graph.root);
}
