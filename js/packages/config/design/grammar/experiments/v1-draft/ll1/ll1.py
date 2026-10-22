import re, sys, itertools
src = open(sys.argv[1]).read().split("%%")[1]
src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
G = {}
for rule in src.split(";"):
    if ":" not in rule: continue
    lhs, rhs = rule.split(":", 1)
    G[lhs.strip()] = [alt.split() for alt in rhs.split("|")]
NT = set(G); E = "ε"
first = {n: set() for n in NT}
def fseq(seq):
    out = set()
    for s in seq:
        f = first[s] if s in NT else {s}
        out |= f - {E}
        if E not in f: return out
    return out | {E}
changed = True
while changed:
    changed = False
    for n, alts in G.items():
        for a in alts:
            f = fseq(a)
            if not f <= first[n]: first[n] |= f; changed = True
start = next(iter(G)); follow = {n: set() for n in NT}; follow[start].add("$")
changed = True
while changed:
    changed = False
    for n, alts in G.items():
        for a in alts:
            for i, s in enumerate(a):
                if s not in NT: continue
                f = fseq(a[i+1:]); add = (f - {E}) | (follow[n] if E in f else set())
                if not add <= follow[s]: follow[s] |= add; changed = True
conflicts = 0
for n, alts in G.items():
    preds = [((fseq(a) - {E}) | (follow[n] if E in fseq(a) else set())) for a in alts]
    for (i, p), (j, q) in itertools.combinations(enumerate(preds), 2):
        if p & q: conflicts += 1; print(f"LL(1) CONFLICT {n}: alt{i} vs alt{j} on {sorted(p & q)}")
print("FOLLOW(rest) =", sorted(follow["rest"]), " FOLLOW(after) =", sorted(follow["after"]))
print(f"{len(G)} nonterminals, {sum(len(a) for a in G.values())} alternatives, {conflicts} LL(1) conflicts")
