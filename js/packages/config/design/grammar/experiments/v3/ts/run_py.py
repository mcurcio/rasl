# tree-sitter (py-tree-sitter native wheel + grammar compiled as a shared library) on the shared corpus.
import sys, json, hashlib, ctypes
from tree_sitter import Language, Parser
lib = ctypes.cdll.LoadLibrary(sys.argv[2]); lib.tree_sitter_rasl.restype = ctypes.c_void_p
parser = Parser(Language(lib.tree_sitter_rasl()))
CONCEPT = {'document', 'directive', 'block', 'slice', 'list'}
LEAF = {'word': 'Word', 'string': 'String', 'space': 'Space', 'comment': 'Comment', 'newline': 'Newline', 'bom': 'Bom'}
for case in json.load(open(sys.argv[1], encoding='utf-8')):
    src = case['src']; b = src.encode('utf-8'); tree = parser.parse(b); root = tree.root_node
    cp = lambda byte: len(b[:byte].decode('utf-8'))
    if root.has_error:
        first = []
        def find(n):
            if first: return
            if n.is_error or n.is_missing: first.append(n); return
            for c in n.children: find(c)
        find(root); f = first[0] if first else None
        print(case['name'].ljust(24), 'REJECT@%s%s' % (cp(f.start_byte) if f else '?', ' (MISSING %s)' % f.type if f and f.is_missing else '')); continue
    out, leaves, st = [], [], {'pos': root.start_byte, 'gaps': False}
    if root.start_byte == 3 and src[0] == '\ufeff': leaves.append(src[0])
    def walk(n):
        if n.type in CONCEPT: out.append('(' + n.type)
        if n.type == 'document' and len(leaves) == 1: out.append('Bom' + json.dumps(leaves[0], ensure_ascii=False))
        if n.type not in CONCEPT and (n.child_count == 0 or n.type in LEAF):
            if n.start_byte != st['pos']: st['gaps'] = True
            st['pos'] = n.end_byte; t = b[n.start_byte:n.end_byte].decode('utf-8')
            leaves.append(t); out.append(LEAF.get(n.type, n.type) + json.dumps(t, ensure_ascii=False)); return
        for c in n.children: walk(c)
        if n.type in CONCEPT: out.append(')')
    walk(root)
    if st['pos'] != len(b): st['gaps'] = True
    s = ' '.join(out)
    print(case['name'].ljust(24), 'ACCEPT rt=%s %s' % (str(''.join(leaves) == src and not st['gaps']).lower(), 'sha:' + hashlib.sha1(s.encode()).hexdigest()[:12] if len(s) > 160 else s))
