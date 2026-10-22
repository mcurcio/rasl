from lark import Lark
from lark.exceptions import LarkError
p = Lark(open("config_regular.lark").read(), start="document", parser="lalr", lexer="basic", strict=True)
for s in ["x //c", "x /a", "x / y"]:
    try: print(repr(s), [ (t.type, str(t)) for t in p.lex(s)])
    except LarkError as e: print(repr(s), "LEX ERROR", type(e).__name__)
