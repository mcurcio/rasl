"""Grammar-based input generation from the normative file (via rex -xmlonly):
random bounded derivations of the syntax rules, each terminal rendered from a
sample of lexemes, then a mutation pass (delete / duplicate / insert a char)."""
import sys, random, json, xml.etree.ElementTree as ET
NS = '{http://www.w3.org/2001/03/XPath/grammar}'
src = open(sys.argv[1], encoding='utf-8').read()
root = ET.fromstring(src.split('<?TOKENS?>')[0] + '</g:grammar>')
prods = {p.get('name'): p for p in root.findall(NS + 'production')}
LEX = {
  'Word': ['a', 'listen', '80', '-1', '0.5', '1e+5', 'color:hsl', 'a#b', '/etc/x', 'x.y', '200ms', 'true', '0x10', '007'],
  'String': ['"a"', "'b'", '"a\\"b"', "'it\\'s'", '"\\n\\t"', '"x y"', '"é"', '"\\q"'],
  'Space': [' ', '\t', '  '], 'Comment': ['# c', '#', '# é'], 'Newline': ['\n', '\r\n'],
  'Bom': ['﻿'], 'EOF': [''],
}
def expand(e, depth, out):
    tag = e.tag[len(NS):]
    if tag == 'ref':
        n = e.get('name')
        if n in prods:
            if depth > 7: return False
            return all(expand(c, depth + 1, out) for c in prods[n])
        out.append((n, random.choice(LEX[n]))); return True
    if tag == 'string': out.append((e.text, e.text)); return True
    if tag == 'sequence': return all(expand(c, depth, out) for c in e)
    if tag == 'choice':
        kids = list(e); random.shuffle(kids)
        for k in kids:
            mark = len(out)
            if expand(k, depth, out): return True
            del out[mark:]
        return False
    reps = {'optional': (0, 1), 'zeroOrMore': (0, 3), 'oneOrMore': (1, 3)}[tag]
    n = random.randint(*reps) if depth <= 7 else reps[0]
    for _ in range(n):
        mark = len(out)
        if not all(expand(c, depth, out) for c in e):
            del out[mark:]; break
    return True
random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
N = int(sys.argv[2])
for i in range(N):
    out = []
    if not all(expand(c, 0, out) for c in prods['Document']): continue
    text = ''.join(t for _, t in out)
    kinds = [k for k, t in out if k != 'EOF']
    print(json.dumps({'src': text, 'gen': True, 'kinds': kinds}))
    for _ in range(2):
        if not text: break
        j = random.randrange(len(text)); op = random.choice('dip')
        m = text[:j] + text[j+1:] if op == 'd' else text[:j] + text[j] + text[j:] if op == 'p' else text[:j] + random.choice(' []{}:;,#"\'\n\rx-') + text[j:]
        print(json.dumps({'src': m, 'gen': False}))
