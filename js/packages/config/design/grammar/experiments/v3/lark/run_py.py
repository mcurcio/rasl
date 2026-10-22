import sys, json, hashlib
from lark import Lark, Tree, Token
from lark.exceptions import UnexpectedInput
p = Lark(open(sys.argv[2]).read(), parser='lalr', lexer='contextual', keep_all_tokens=True)
CONCEPT = {'start': 'document', 'directive': 'directive', 'last_directive': 'directive', 'block': 'block', 'slice': 'slice', 'list': 'list'}
LEAF = {'WORD': 'Word', 'STRING': 'String', 'SPACE': 'Space', 'COMMENT': 'Comment', 'NEWLINE': 'Newline', 'BOM': 'Bom'}
for c in json.load(open(sys.argv[1], encoding='utf-8')):
    src = c['src']
    try: t = p.parse(src)
    except UnexpectedInput as e: print(c['name'].ljust(24), 'REJECT@%d  %s' % (e.pos_in_stream if e.pos_in_stream is not None else -1, type(e).__name__)); continue
    out, leaves = [], []
    def walk(n):
        if isinstance(n, Token): leaves.append(str(n)); out.append(LEAF.get(n.type, str(n)) + json.dumps(str(n), ensure_ascii=False)); return
        k = CONCEPT.get(n.data)
        if k: out.append('(' + k)
        for ch in n.children: walk(ch)
        if k: out.append(')')
    walk(t); s = ' '.join(out)
    print(c['name'].ljust(24), 'ACCEPT rt=%s %s' % (str(''.join(leaves) == src).lower(), 'sha:' + hashlib.sha1(s.encode()).hexdigest()[:12] if len(s) > 160 else s))
