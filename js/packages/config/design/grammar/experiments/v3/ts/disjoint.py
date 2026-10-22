# Token-disjointness check read straight from tree-sitter's generated grammar.json (no second grammar file).
import json, re, sys, itertools, interegular
g = json.load(open(sys.argv[1]))
def rx(n):
    t = n['type']
    if t == 'STRING': return re.escape(n['value'])
    if t == 'PATTERN': return '(?:%s)' % n['value']
    if t == 'SEQ': return ''.join(rx(m) for m in n['members'])
    if t == 'CHOICE': return '(?:%s)' % '|'.join(rx(m) for m in n['members'])
    if t == 'REPEAT': return '(?:%s)*' % rx(n['content'])
    if t == 'REPEAT1': return '(?:%s)+' % rx(n['content'])
    if t in ('TOKEN', 'IMMEDIATE_TOKEN'): return rx(n['content'])
    if t == 'BLANK': return ''
    raise ValueError(t)
def is_token(n):  # a rule made only of terminals
    t = n['type']
    if t in ('TOKEN', 'STRING', 'PATTERN'): return True
    if t in ('SEQ', 'CHOICE'): return all(is_token(m) for m in n['members'])
    if t in ('REPEAT', 'REPEAT1'): return is_token(n['content'])
    return False
toks = {k: rx(v) for k, v in g['rules'].items() if is_token(v)}
anon = set()
def lits(n):
    if isinstance(n, dict):
        if n.get('type') == 'STRING': anon.add(n['value'])
        for v in n.values(): lits(v)
    elif isinstance(n, list): [lits(v) for v in n]
for k, v in g['rules'].items():
    if not is_token(v): lits(v)
for a in anon: toks.setdefault(repr(a), re.escape(a))
fsms = {k: interegular.parse_pattern(v).to_fsm() for k, v in toks.items()}
bad = [(a, b) for a, b in itertools.combinations(fsms, 2) if not fsms[a].intersection(fsms[b]).empty()]
print(len(toks), 'token kinds,', len(bad), 'overlapping pairs', bad); sys.exit(1 if bad else 0)
