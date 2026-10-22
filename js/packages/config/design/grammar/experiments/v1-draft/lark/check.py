import sys, pathlib
from lark import Lark
from lark.exceptions import LarkError
g = pathlib.Path(sys.argv[1]).read_text()
p = Lark(g, start="document", parser="lalr", lexer="basic", strict=True)
print("STRICT LALR(1) BUILD OK: no shift/reduce or reduce/reduce conflicts, no terminal collisions")
print("terminals:", sorted(t.name for t in p.terminals))
root = pathlib.Path("/Volumes/Dock/Home/Code/rasl/.claude/worktrees/friendly-saha-6a52d1")
for f in ["hyperhdr.conf","family_room.conf","virtual.conf","js/test.conf","js/external-test.conf"]:
    try: p.parse((root/f).read_text()); print("ACCEPT", f)
    except LarkError as e: print("REJECT", f, str(e).splitlines()[0])
cases = ["connect a[0:3]","connect a[3:]","connect a[:3]","connect a[:]","connect a[1]","connect a [0:3]",
         "model color:hsl","x 200ms","x -0.5","x :80","x a#b","color #fff","x a=b","x [1, 2,]","x [1;2]",
         "x [1 2]","a {} b","a\n{\n}","a { b }","x \"a\\qb\"","x 127.0.0.1:80","x http://a/b","x [\n 1,\n # c\n 2\n]",
         "a b c","x [[1],[2]]","x []","x é😀","1 x","x \"a\"\"b\"", "x a\rb"]
for c in cases:
    try: p.parse(c); r="ACCEPT"
    except LarkError as e: r="REJECT " + type(e).__name__
    print(f"  {c!r:28} {r}")
