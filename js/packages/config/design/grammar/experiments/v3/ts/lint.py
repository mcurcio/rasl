# CI lint: the generated grammar.json must use none of tree-sitter's conflict-silencing features.
import json, sys
g = json.load(open(sys.argv[1]))
bad = []
if g.get('conflicts'): bad.append('conflicts: %s' % g['conflicts'])
if g.get('precedences'): bad.append('precedences')
if g.get('externals'): bad.append('externals (hand-written C scanner)')
if g.get('extras'): bad.append('extras (implicit whitespace)')
if g.get('reserved'): bad.append('reserved (keyword reservation changes lexing)')
if g.get('word'): bad.append('word (keyword extraction changes lexing)')
if g.get('inline'): bad.append('inline')
def walk(n, rule):
    if isinstance(n, dict):
        t = n.get('type', '')
        if t.startswith('PREC'): bad.append('%s in rule %s' % (t, rule))
        for v in n.values(): walk(v, rule)
    elif isinstance(n, list):
        for v in n: walk(v, rule)
for name, r in g['rules'].items(): walk(r, name)
print('\n'.join(bad) or 'clean'); sys.exit(1 if bad else 0)
