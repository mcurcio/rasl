# Driver: corpus -> REx-comparable lines (stdout) and canonical CST JSON lines (argv[2]).
import sys, os, json, hashlib
here = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [here, os.path.join(here, '..', 'gen-py')]
sys.setrecursionlimit(20000)
from antlr4 import InputStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener
from RaslLexer import RaslLexer as L
from RaslParser import RaslParser as P
from recovery import RaslRecovery
from cst import to_cst
LEAF = {'WORD': 'Word', 'STRING': 'String', 'SPACE': 'Space', 'COMMENT': 'Comment', 'NEWLINE': 'Newline', 'BOM': 'Bom'}
class Count(ErrorListener):
    n = 0
    def syntaxError(self, *a): Count.n += 1
canon = lambda v: json.dumps(v, ensure_ascii=True, separators=(',', ':'))
jl, out_lines = [], []
for case in json.load(open(sys.argv[1], encoding='utf-8')):
    name, src = case['name'], case['src']
    lexer = L(InputStream(src)); lexer.removeErrorListeners(); lexer.addErrorListener(Count())
    ts = CommonTokenStream(lexer); ts.fill()
    parser = P(ts); parser.removeErrorListeners(); rec = RaslRecovery()
    if not os.environ.get('DEFAULT'): parser._errHandler = rec
    if os.environ.get('NOHEUR'): parser._interp.getSynValidOrSemInvalidAltThatFinishedDecisionEntryRule = lambda c, o: 0
    crash, tree, seen = '', ['document', 0, 0, []], []
    try: tree, seen = to_cst(parser.document())
    except Exception as e: crash = type(e).__name__
    toks = [t for t in ts.tokens if t.type != -1]
    tokens = [[P.symbolicNames[t.type], t.text] for t in toks]
    rt = ''.join(t[1] for t in tokens) == src
    cover = seen == list(range(len(toks)))
    jl.append(canon({'name': name, 'tokens': tokens, 'tree': tree, 'diags': rec.diags, 'rt': rt, 'cover': cover, 'crash': crash}))
    if rec.diags or crash:
        out_lines.append(name.ljust(24) + ' REJECT@' + (str(rec.diags[0]['offset']) if rec.diags else 'CRASH')); continue
    out = []
    def sx(n):
        out.append('(' + n[0]); i = n[1]
        for k in n[3] + [None]:
            stop = k[1] if k else n[2]
            while i < stop:
                t = toks[i]; out.append(LEAF.get(P.symbolicNames[t.type], t.text) + json.dumps(t.text, ensure_ascii=False)); i += 1
            if k: sx(k); i = k[2]
        out.append(')')
    sx(tree); s = ' '.join(out)
    out_lines.append(name.ljust(24) + ' ACCEPT rt=%s %s' % (str(rt).lower(), 'sha:' + hashlib.sha1(s.encode()).hexdigest()[:12] if len(s) > 160 else s))
sys.stdout.buffer.write(('\n'.join(out_lines) + '\n').encode('utf-8', 'surrogatepass'))
open(sys.argv[2], 'w').write('\n'.join(jl) + '\n')
print('lexer errors:', Count.n, file=sys.stderr)
