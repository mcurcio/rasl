# ANTLR4 Python3 target on the shared corpus; same normalized output.
import sys, json, hashlib
sys.path.insert(0, sys.argv[2])
from antlr4 import InputStream, CommonTokenStream, ParserRuleContext
from antlr4.tree.Tree import TerminalNode
from antlr4.error.ErrorListener import ErrorListener
from RaslLexer import RaslLexer
from RaslParser import RaslParser
CONCEPT = {'document': 'document', 'directive': 'directive', 'lastDirective': 'directive', 'block': 'block', 'slicedWord': 'slice', 'list': 'list'}
LEAF = {'WORD': 'Word', 'STRING': 'String', 'SPACE': 'Space', 'COMMENT': 'Comment', 'NEWLINE': 'Newline', 'BOM': 'Bom'}
class First(ErrorListener):
    def __init__(self): self.at = -1; self.msgs = []
    def syntaxError(self, r, tok, line, col, msg, e):
        if self.at < 0: self.at = tok.start if tok else -2
        self.msgs.append('%d:%d %s' % (line, col, msg))
verbose = len(sys.argv) > 3
for case in json.load(open(sys.argv[1], encoding='utf-8')):
    src = case['src']; lexer = RaslLexer(InputStream(src)); lexer.removeErrorListeners()
    parser = RaslParser(CommonTokenStream(lexer)); err = First(); parser.removeErrorListeners(); parser.addErrorListener(err)
    tree = parser.document()
    if err.at != -1:
        print(case['name'].ljust(24), 'REJECT@%d' % err.at + ('  ' + ' | '.join(err.msgs) + '\n    tree: ' + tree.toStringTree(recog=parser) if verbose else '')); continue
    out, leaves = [], []
    def walk(n):
        if isinstance(n, TerminalNode):
            t = n.symbol
            if t.type == -1: return
            sym = RaslParser.symbolicNames[t.type] if t.type < len(RaslParser.symbolicNames) else ''
            leaves.append(t.text); out.append(LEAF.get(sym, t.text) + json.dumps(t.text, ensure_ascii=False)); return
        c = CONCEPT.get(parser.ruleNames[n.getRuleIndex()])
        if c: out.append('(' + c)
        for k in (n.children or []): walk(k)
        if c: out.append(')')
    walk(tree); s = ' '.join(out)
    print(case['name'].ljust(24), 'ACCEPT rt=%s %s' % (str(''.join(leaves) == src).lower(), 'sha:' + hashlib.sha1(s.encode()).hexdigest()[:12] if len(s) > 160 else s))
