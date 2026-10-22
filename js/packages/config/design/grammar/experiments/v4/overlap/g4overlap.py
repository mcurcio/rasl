"""Token-overlap check for the lexer rules of a .g4 (the subset Rasl.g4 uses): each non-fragment
lexer rule becomes a regex over code points; interegular decides, for every pair, whether some
string matches both. Refuses lexer commands, modes, actions, predicates and non-greedy loops."""
import re, sys, itertools, interegular
src = open(sys.argv[1], encoding='utf-8').read()
def die(m): sys.exit('g4overlap: refused: ' + m)
TOK = re.compile(r"""\s+|//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\])*'|~?\[(?:\\.|[^\]\\])*\]|[A-Za-z_][A-Za-z0-9_]*|->|\*\?|\+\?|\?\?|[:;|()?*+~.{}]""", re.S)
toks, pos = [], 0
while pos < len(src):
    m = TOK.match(src, pos)
    if not m: die('text %r' % src[pos:pos + 20])
    pos = m.end(); t = m.group()
    if not (t.isspace() or t.startswith('//') or t.startswith('/*')): toks.append(t)
def esc(s, i):
    """ANTLR escape at s[i] == '\\' -> (code point, next index)."""
    c = s[i + 1]
    if c == 'u':
        if s[i + 2] == '{': j = s.index('}', i); return int(s[i + 3:j], 16), j + 1
        return int(s[i + 2:i + 6], 16), i + 6
    return {'t': 9, 'n': 10, 'r': 13, 'f': 12, 'b': 8}.get(c, ord(c)), i + 2
def ranges(body):
    rng, i = [], 0
    while i < len(body):
        a, i = esc(body, i) if body[i] == '\\' else (ord(body[i]), i + 1)
        if i + 1 < len(body) and body[i] == '-':
            b, i = esc(body, i + 1) if body[i + 1] == '\\' else (ord(body[i + 1]), i + 2); rng.append((a, b))
        else: rng.append((a, a))
    return rng
CUTS = {0, 0x110000}
def classes():
    """Alphabet compression: code points split into intervals no set boundary crosses; each
    interval is one symbol (a representative character), so the FSMs stay small."""
    cuts = sorted(CUTS); return list(zip(cuts, cuts[1:]))
def rep(k): return re.escape(chr(0x4E00 + k))
def cls(body, neg):
    rng, out = ranges(body), []
    for k, (lo, hi) in enumerate(classes()):
        inside = any(a <= lo and hi - 1 <= b for a, b in rng)
        if inside != neg: out.append(rep(k))
    return '[' + ''.join(out) + ']'
def lit_char(c):
    k = next(k for k, (lo, hi) in enumerate(classes()) if lo <= c < hi); return rep(k)
rules, frags, i = {}, {}, 3
while i < len(toks):
    frag = toks[i] == 'fragment'; i += frag
    name = toks[i]; j = toks.index(';', i); body = toks[i + 2:j]; i = j + 1
    if not name[0].isupper(): continue
    for t in body:
        if t in ('->', '{', '}', '*?', '+?', '??', 'mode'): die('%r in %s' % (t, name))
    (frags if frag else rules)[name] = body
def rx(body):
    out = []
    for t in body:
        if t.startswith("'"):
            s, k, lit = t[1:-1], 0, ''
            while k < len(s):
                c, k = esc(s, k) if s[k] == '\\' else (ord(s[k]), k + 1); lit += lit_char(c)
            out.append('(?:' + lit + ')')
        elif t.startswith('~['): out.append(cls(t[2:-1], True))
        elif t.startswith('['): out.append(cls(t[1:-1], False))
        elif t in frags: out.append('(?:' + rx(frags[t]) + ')')
        elif t == '.': die('wildcard')
        elif t == '~': die('~ before a non-set')
        elif t[0].isupper(): die('token reference %s inside a lexer rule' % t)
        else: out.append(t)                                  # ( ) | ? * +
    return ''.join(out)
for body in list(rules.values()) + list(frags.values()):
    for t in body:
        if t.startswith('~[') or t.startswith('['):
            for a, b in ranges(t[t.index('[') + 1:-1]): CUTS.update((a, b + 1))
        elif t.startswith("'"):
            q, k = t[1:-1], 0
            while k < len(q):
                c, k = esc(q, k) if q[k] == '\\' else (ord(q[k]), k + 1); CUTS.update((c, c + 1))
print('alphabet: %d symbol classes' % len(classes()))
fsm = {n: interegular.parse_pattern(rx(b)).to_fsm() for n, b in rules.items()}
bad = 0
for a, b in itertools.combinations(rules, 2):
    common = fsm[a] & fsm[b]
    if not common.empty():
        bad += 1; ex = next(iter(common.strings()))
        w = ''.join(chr(classes()[ord(str(x)) - 0x4E00][0]) for x in ex)
        print('OVERLAP %s / %s, e.g. %r' % (a, b, w))
print('%d token kinds, %d pairs, %d overlapping' % (len(rules), len(rules) * (len(rules) - 1) // 2, bad))
sys.exit(1 if bad else 0)
