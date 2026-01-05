import { serializeCst } from "./cst.js";
import type { IDocumentGraph } from "./graph.js";
import type { DocumentWriter } from "./io.js";

/**
 * Persist all modified documents in a graph back to their resolved paths.
 *
 * A document is considered modified if `serializeCst(node.cst)` differs from
 * the original `node.source` as loaded.
 */
export async function save(graph: IDocumentGraph, writer: DocumentWriter): Promise<void> {
  for (const node of graph.nodes.values()) {
    const next = serializeCst(node.cst);
    if (next !== node.source) {
      await writer.write(node.resolvedPath, next);
    }
  }
}
