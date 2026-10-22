"""Mechanical .g4 -> Bison translation for the subset Rasl.g4 uses. Parser rules only; lexer
rules just name the tokens. Refuses anything outside the subset (actions, predicates, lexer
commands and modes, options, labels, wildcards, negation, non-greedy loops, rule arguments), so a
construct ANTLR resolves silently can never slip past the check. EBNF operators become fresh
nonterminals with the textbook expansions; EOF is allowed only at the end of the start rule."""
import re, sys
src = open(sys.argv[1], encoding='utf-8').read()

def die(msg): sys.exit('g4bison: refused: ' + msg)

# --- tokenize the grammar file -------------------------------------------------------------
TOK = re.compile(r"""\s+|//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\])*'|\[(?:\\.|[^\]\\])*\]|[A-Za-z_][A-Za-z0-9_]*|->|\+=|\*\?|\+\?|\?\?|[:;|()?*+~.=#@{}<>,]""", re.S)
toks, pos = [], 0
while pos < len(src):
    m = TOK.match(src, pos)
    if not m: die('unexpected text %r' % src[pos:pos + 20])
    pos = m.end(); t = m.group()
    if not (t.isspace() or t.startswith('//') or t.startswith('/*')): toks.append(t)
if toks[:1] != ['grammar'] or toks[2] != ';': die('expected a combined "grammar X;" header')
toks = toks[3:]
# --- split into rules --------------------------------------------------------------------------
rules, lexer, order, i = {}, {}, [], 0
while i < len(toks):
    frag = toks[i] == 'fragment'
    if frag: i += 1
    name = toks[i]
    if name in ('options', 'tokens', 'channels', 'import', 'mode', '@') or name.startswith('@'): die('"%s" section' % name)
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) or toks[i + 1] != ':': die('rule header at %r' % toks[i:i + 3])
    j = toks.index(';', i)
    body = toks[i + 2:j]; i = j + 1
    if name[0].isupper():
        if '->' in body: die('lexer command in %s' % name)
        if '{' in body: die('action or predicate in lexer rule %s' % name)
        if not frag: lexer[name] = body
    else:
        for t in body:
            if t in ('{', '}', '=', '+=', '#', '~', '.', '<', '>', '*?', '+?', '??', ',', '@', '->') or t.startswith('['):
                die('"%s" in parser rule %s' % (t, name))
        rules[name] = body; order.append(name)
# implicit literal tokens map to the lexer rule whose whole body is that literal (ANTLR's rule)
literal = {b[0]: n for n, b in lexer.items() if len(b) == 1 and b[0].startswith("'")}
# --- translate ---------------------------------------------------------------------------------
out, used, n = {}, set(), [0]
def fresh(base): n[0] += 1; return '%s_%d' % (base, n[0])
def parse_alts(ts, k, owner):
    alts, cur = [], []
    while k < len(ts) and ts[k] != ')':
        if ts[k] == '|': alts.append(cur); cur = []; k += 1; continue
        if ts[k] == '(':
            sub, k = parse_alts(ts, k + 1, owner)
            if k >= len(ts) or ts[k] != ')': die('unbalanced ( in %s' % owner)
            k += 1; sym = fresh(owner + '_grp'); out[sym] = sub
        else:
            t = ts[k]; k += 1
            if t.startswith("'"):
                if t not in literal: die('literal %s has no lexer rule (implicit tokens unsupported)' % t)
                sym = literal[t]
            elif t == 'EOF':
                sym = '$EOF'
            elif t[0].isupper():
                if t not in lexer: die('unknown token %s' % t)
                sym = t
            else:
                if t not in rules: die('unknown rule %s' % t)
                sym = t
        if k < len(ts) and ts[k] in ('?', '*', '+'):
            op = ts[k]; k += 1; base = sym; sym = fresh(owner + {'?': '_opt', '*': '_star', '+': '_plus'}[op])
            out[sym] = {'?': [[], [base]], '*': [[], [sym, base]], '+': [[base], [sym, base]]}[op]
        cur.append(sym)
    alts.append(cur)
    return alts, k
for r in order:
    alts, k = parse_alts(rules[r], 0, r)
    if k != len(rules[r]): die('unbalanced ) in %s' % r)
    out[r] = alts
start = order[0]
for name, alts in out.items():
    for a in alts:
        for idx, s in enumerate(a):
            if s == '$EOF' and not (name == start and idx == len(a) - 1): die('EOF outside the end of the start rule')
        a[:] = [s for s in a if s != '$EOF']
        used.update(s for s in a if s in lexer)
print('%%token %s' % ' '.join(sorted(used)))
print('%expect 0\n%start ' + start + '\n%%')
for name, alts in out.items():
    print('%s\n  : %s\n  ;' % (name, '\n  | '.join(' '.join(a) if a else '/* empty */' for a in alts)))
print('%%')
