# Compare every tool's verdicts and accepted trees against the REx TS parser; also exact lines (incl. error offsets).
import json, sys, collections
src = {c['name']: c['src'] for c in json.load(open('corpus/gen.json'))}
def load(f):
    d = {}
    for l in open(f, encoding='utf-8'):
        name, rest = l.rstrip('\n').split(None, 1)
        d[name] = rest.split('  ')[0].strip()
    return d
base = load('gen-out/rex_ts.txt')
acc = sum(v.startswith('ACCEPT') for v in base.values())
print('base rex_ts: %d inputs, %d accepted, %d rejected, round-trip failures %d' % (len(base), acc, len(base) - acc, sum('rt=false' in v for v in base.values())))
for f in ['rex_py', 'ts_ts', 'ts026_ts', 'ts_py', 'antlr_ts', 'antlr_py', 'lark_py']:
    d = load('gen-out/%s.txt' % f)
    verdict = [n for n in base if base[n].split('@')[0].split()[0] != d[n].split('@')[0].split()[0]]
    tree = [n for n in base if base[n].startswith('ACCEPT') and d[n].startswith('ACCEPT') and base[n] != d[n]]
    exact = sum(base[n] == d[n] for n in base)
    nul = sum('\x00' in src[n] for n in verdict)
    rt = sum('rt=false' in v for v in d.values())
    print('%-9s verdict-diffs %3d (with NUL %d)  tree-diffs %d  identical-lines %d/%d  rt-failures %d' % (f, len(verdict), nul, len(tree), exact, len(base), rt))
    for n in verdict[:2]:
        if '\x00' not in src[n]: print('    e.g.', json.dumps(src[n]), base[n][:40], '|', d[n][:40])
print('NUL-containing inputs in corpus:', sum('\x00' in s for s in src.values()))
