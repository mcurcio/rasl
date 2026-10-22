# ANTLR parse tree -> normalised CST: concept nodes over token ranges; grammar-internal rules transparent.
from antlr4.tree.Tree import TerminalNode, ErrorNode
from RaslParser import RaslParser as P
CONCEPT = {'document': 'document', 'directive': 'directive', 'lastDirective': 'directive',
           'block': 'block', 'slicedWord': 'slice', 'list': 'list'}

def to_cst(tree):
    """Returns the tree and the token indices of its terminals in tree order (EOF and conjured tokens excluded)."""
    seen = []
    def items(n):
        if isinstance(n, TerminalNode):
            t = n.symbol
            if t.type == -1 or t.tokenIndex < 0: return []
            seen.append(t.tokenIndex)
            return [('E' if isinstance(n, ErrorNode) else 'T', t.tokenIndex, n.parentCtx)]
        kids = [x for k in (n.children or []) for x in items(k)]
        c = CONCEPT.get(P.ruleNames[n.getRuleIndex()])
        return [node(c, kids, n)] if c else kids
    def node(kind, kids, ctx):
        ch, lo, hi, i = [], None, None, 0
        def span(a, b):
            nonlocal lo, hi
            lo = a if lo is None else min(lo, a); hi = b if hi is None else max(hi, b)
        while i < len(kids):
            k = kids[i]
            if k[0] == 'E':                               # a run of error terminals of one parse-tree parent -> one error node
                j = i
                while j + 1 < len(kids) and kids[j + 1][0] == 'E' and kids[j + 1][2] is k[2]: j += 1
                ch.append(['error', k[1], kids[j][1] + 1, []]); span(k[1], kids[j][1] + 1); i = j
            elif k[0] == 'T': span(k[1], k[1] + 1)
            else: ch.append(k); span(k[1], k[2])
            i += 1
        if lo is None: lo = hi = ctx.start.tokenIndex if ctx.start is not None else 0
        return [kind, lo, hi, ch]
    return items(tree)[0], seen
