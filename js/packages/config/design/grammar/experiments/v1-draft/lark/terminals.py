# Pairwise disjointness of the lexical grammar's token languages (pure regular, no lookaround).
import itertools, interegular
D = r""" \t\r\n;{}\[\],"'\x00-\x1f\x7f"""          # delimiters + controls
T = rf"[^{D}]"                                      # word char
H = rf"[^{D}#:/]"                                   # word head (not # : /)
N = rf"[^{D}/*]"                                    # char allowed right after a leading '/'
SLICE = r"\[(?:[0-9]+:[0-9]*|:[0-9]+)\]"
terms = {
  "WORD":          rf"(?:{H}{T}*|/(?:{N}{T}*)?)(?:{SLICE})?",
  "BAD_SLICE(err)":rf"(?:{H}{T}*|/(?:{N}{T}*)?)\[",   # longest match: wins over WORD unless a valid slice follows
  "STRING":        r""""(?:[^"\\\r\n]|\\[\\nrt"'])*"|'(?:[^'\\\r\n]|\\[\\nrt"'])*'""",
  "NEWLINE":       r"\r?\n",
  "WS":            r"[ \t]+",
  "LINE_COMMENT":  r"(?:#|//)[^\r\n]*",
  "BLOCK_COMMENT": r"/\*(?:[^*]|\*+[^*/])*\*+/",
  "PUNCT":         r"[;{}\[\],]",
}
fsms = {k: interegular.parse_pattern(v).to_fsm() for k, v in terms.items()}
bad = 0
for a, b in itertools.combinations(terms, 2):
    i = fsms[a] & fsms[b]
    if not i.empty():
        bad += 1; print(f"OVERLAP {a} / {b}: e.g. {''.join(next(iter(i.strings())))!r}")
print(f"{len(list(itertools.combinations(terms,2)))} pairs checked, {bad} overlapping")
# prefix relations matter for longest-match: report which token languages contain a proper prefix of another
