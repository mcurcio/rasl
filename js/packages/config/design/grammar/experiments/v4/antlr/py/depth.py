import sys, os, json
here = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [here, os.path.join(here, '..', 'gen-py')]
from antlr4 import InputStream, CommonTokenStream
from RaslLexer import RaslLexer as L
from RaslParser import RaslParser as P
from recovery import RaslRecovery
from cst import to_cst
print('python recursion limit', sys.getrecursionlimit())
for c in json.load(open(sys.argv[1])):
    ts = CommonTokenStream(L(InputStream(c['src']))); ts.fill(); p = P(ts); p.removeErrorListeners(); r = RaslRecovery(); p._errHandler = r
    try: to_cst(p.document()); res = 'ok diags=%d' % len(r.diags)
    except RecursionError: res = 'RecursionError'
    print(' ', c['name'].ljust(14), res)
