import itertools, interegular
D = r""" \t\r\n;{}\[\],"'\x00-\x1f\x7f"""
T = rf"[^{D}]"; H = rf"[^{D}#:/]"; N = rf"[^{D}/*]"
HEADW = rf"(?:{H}{T}*|/(?:{N}{T}*)?)"
SLICE = r"\[(?:[0-9]+:[0-9]*|:[0-9]+)\]"
ok = r"""[^"\\\r\n]|\\[\\nrt"']"""; anyc = r"""[^"\\\r\n]|\\[^\r\n]"""
oks = r"""[^'\\\r\n]|\\[\\nrt"']"""; anys = r"""[^'\\\r\n]|\\[^\r\n]"""
terms = {
  "WORD": rf"{HEADW}(?:{SLICE})?",
  "STRING": rf'"(?:{ok})*"|\'(?:{oks})*\'',
  "NEWLINE": r"\r?\n", "WS": r"[ \t]+",
  "LINE_COMMENT": r"(?:#|//)[^\r\n]*",
  "BLOCK_COMMENT": r"/\*(?:[^*]|\*+[^*/])*\*+/",
  "PUNCT": r"[;{}\[\],]",
  # error tokens (lexical error productions; each maps to one diagnostic code)
  "E_BAD_SLICE": rf"{HEADW}\[",
  "E_BAD_ESCAPE": rf'"(?:{ok})*\\[^\\nrt"\'\r\n](?:{anyc})*"|\'(?:{oks})*\\[^\\nrt"\'\r\n](?:{anys})*\'',
  "E_UNTERMINATED_STRING": rf'"(?:{anyc})*\\?|\'(?:{anys})*\\?',
  "E_UNTERMINATED_COMMENT": r"/\*(?:[^*]|\*+[^*/])*\**",
  "E_STRAY_CHAR": r"[:\r\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
}
f = {k: interegular.parse_pattern(v).to_fsm() for k, v in terms.items()}
bad = [(a, b, ''.join(next(iter((f[a] & f[b]).strings())))) for a, b in itertools.combinations(terms, 2) if not (f[a] & f[b]).empty()]
for a, b, ex in bad: print("OVERLAP", a, b, repr(ex))
print(f"{len(terms)} token kinds, {len(terms)*(len(terms)-1)//2} pairs, {len(bad)} overlapping")
