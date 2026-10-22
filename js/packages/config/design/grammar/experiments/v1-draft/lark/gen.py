import json, sys, pathlib, random
from hypothesis import given, settings, HealthCheck, strategies as st
from hypothesis.extra.lark import from_lark
from lark import Lark
from lark.exceptions import LarkError
g = pathlib.Path("config_regular.lark").read_text()
p = Lark(g, start="document", parser="lalr", lexer="basic", strict=True)
print("strict build (pure-regular WORD): OK")
ws = st.sampled_from([" ", "  ", "\t", " # c\n", " /* b */ "])
strat = from_lark(Lark(g, start="document", parser="lalr", lexer="basic"), start="document")
out = []
@settings(max_examples=400, deadline=None, suppress_health_check=list(HealthCheck), database=None)
@given(strat)
def collect(s): out.append(s)
collect()
acc = []
rej = 0
for s in out:
    try: p.parse(s); acc.append(s)
    except LarkError: rej += 1
# mutation negatives: delete / duplicate / insert one char
rnd = random.Random(1); muts = []
for s in acc[:300]:
    if not s: continue
    i = rnd.randrange(len(s)); op = rnd.choice("dic")
    m = s[:i]+s[i+1:] if op=="d" else s[:i]+s[i]+s[i:] if op=="c" else s[:i]+rnd.choice(list(';{}[],"\':\n#'))+s[i:]
    try: p.parse(m); muts.append([m, True])
    except LarkError: muts.append([m, False])
json.dump({"pos": acc, "mut": muts}, open("corpus.json","w"))
print(f"generated {len(out)}; reference accepts {len(acc)}, rejects {rej} (adjacent-token merges)")
print(f"mutants {len(muts)}: reference accepts {sum(1 for _,a in muts if a)}, rejects {sum(1 for _,a in muts if not a)}")
print("samples:", [s for s in acc if len(s) > 15][:3])
