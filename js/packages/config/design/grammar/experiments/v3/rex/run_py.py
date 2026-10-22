# REx-generated Python parser on the shared corpus. Same normalized output as run_ts.ts.
import sys, json, hashlib
sys.path.insert(0, sys.argv[2])
import config_py as M
P = M.config_py
CONCEPT = {'Document': 'document', 'Directive': 'directive', 'LastDirective': 'directive', 'Block': 'block', 'SlicedWord': 'slice', 'List': 'list'}
def kind(n):
    n = n[1:-1] if n.startswith("'") and n.endswith("'") and len(n) > 2 else n
    return 'Bom' if n == '﻿' else n
def norm(n, src, out, leaves):
    if isinstance(n, P.Terminal):
        if n.name == 'EOF': return
        t = src[n.begin:n.end]; leaves.append(t); out.append(kind(n.name) + json.dumps(t, ensure_ascii=False)); return
    c = CONCEPT.get(n.name)
    if c: out.append('(' + c)
    for k in n.children: norm(k, src, out, leaves)
    if c: out.append(')')
for case in json.load(open(sys.argv[1], encoding='utf-8')):
    src = case['src']; b = P.ParseTreeBuilder()
    p = P(src, b)
    try:
        p.parse_Document()
        root = b.stack[0]; out = []; leaves = []
        norm(root, src, out, leaves); s = ' '.join(out)
        line = 'ACCEPT rt=%s %s' % (str(''.join(leaves) == src).lower(), 'sha:' + hashlib.sha1(s.encode()).hexdigest()[:12] if len(s) > 160 else s)
    except P.ParseException as e:
        line = 'REJECT@%d' % e.getBegin()
    print(case['name'].ljust(24), line)
