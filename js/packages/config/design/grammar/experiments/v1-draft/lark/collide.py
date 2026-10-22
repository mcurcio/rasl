import interegular, logging
from lark import Lark, logger
logger.setLevel(logging.DEBUG)
pats = {
 "WORD_with_lookahead": r"""(?:[^ \t\r\n;{}\[\],"':\/]|\/(?![\/*]))[^ \t\r\n;{}\[\],"']*(?:\[(?:[0-9]+:[0-9]*|:[0-9]+)\]|(?!\[))""",
 "WORD_no_lookahead":   r"""[^ \t\r\n;{}\[\],"':\/][^ \t\r\n;{}\[\],"']*""",
 "WORD_no_hash_head":   r"""[^ \t\r\n;{}\[\],"'#:\/][^ \t\r\n;{}\[\],"']*""",
 "LINE_COMMENT": r"""(?:#|//)[^\r\n]*""",
}
for a in ["WORD_with_lookahead","WORD_no_lookahead","WORD_no_hash_head"]:
    try:
        fa = interegular.parse_pattern(pats[a]).to_fsm(); fb = interegular.parse_pattern(pats["LINE_COMMENT"]).to_fsm()
        inter = fa & fb
        ex = next(iter(inter.strings()), None) if not inter.empty() else None
        print(f"{a:22} vs LINE_COMMENT: overlap={not inter.empty()} example={''.join(ex) if ex else None!r}")
    except Exception as e:
        print(f"{a:22} vs LINE_COMMENT: interegular could not analyse: {type(e).__name__}: {e}")
