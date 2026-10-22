// ANTLR parse tree -> normalised CST: concept nodes over token ranges; grammar-internal rules transparent.
import P from "../gen-ts/RaslParser.js";

export type Node = [kind: string, start: number, end: number, children: Node[]];
const CONCEPT: Record<string, string> = { document: "document", directive: "directive", lastDirective: "directive",
  block: "block", slicedWord: "slice", list: "list" };

/** Returns the tree and the token indices of its terminals in tree order (EOF and conjured tokens excluded). */
export function toCst(tree: any): { tree: Node; seen: number[] } {
  const seen: number[] = [];
  // items: concept nodes, error terminals ("E"), plain terminals ("T"), in source order
  function items(n: any): any[] {
    if (n.symbol) {
      const t = n.symbol;
      if (t.type === -1 || t.tokenIndex < 0) return [];
      seen.push(t.tokenIndex);
      return [[n.isErrorNode?.() ? "E" : "T", t.tokenIndex, n.parentCtx]];
    }
    const kids = (n.children ?? []).flatMap(items);
    const c = CONCEPT[P.ruleNames[n.ruleIndex]];
    return c ? [node(c, kids, n)] : kids;
  }
  function node(kind: string, kids: any[], ctx: any): Node {
    const ch: Node[] = [];
    let lo = Infinity, hi = -Infinity;
    for (let i = 0; i < kids.length; i++) {
      const k = kids[i];
      if (k[0] === "E") {                                     // a run of error terminals of one parse-tree parent -> one error node
        let j = i; while (j + 1 < kids.length && kids[j + 1][0] === "E" && kids[j + 1][2] === k[2]) j++;
        ch.push(["error", k[1], kids[j][1] + 1, []]); i = j;
        lo = Math.min(lo, k[1]); hi = Math.max(hi, kids[j][1] + 1);
      } else if (k[0] === "T") { lo = Math.min(lo, k[1]); hi = Math.max(hi, k[1] + 1); }
      else { ch.push(k); lo = Math.min(lo, k[1]); hi = Math.max(hi, k[2]); }
    }
    if (lo === Infinity) lo = hi = ctx.start?.tokenIndex ?? 0;
    return [kind, lo, hi, ch];
  }
  return { tree: items(tree)[0], seen };
}
