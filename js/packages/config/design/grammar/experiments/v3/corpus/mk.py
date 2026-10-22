# Writes corpus/cases.json: list of {name, src}. Real files + edge cases.
import json, glob, os
here = os.path.dirname(os.path.abspath(__file__))
cases = []
for f in sorted(glob.glob(os.path.join(here, 'real-*.conf'))):
    cases.append({'name': os.path.basename(f), 'src': open(f, encoding='utf-8').read()})
edge = {
 'simple': 'listen 80;',
 'slices': 'x a[0:3] [1, b[2:]] c[:3]',
 'slice-empty-rejected': 'x a[:]',
 'list-multiline': 'x [a,\n  b, # c\n\n  c,\n]\n',
 'touch-strings': 'x "a""b"',
 'touch-word-string': 'x a"b"',
 'touch-lists': 'x [a][b]',
 'space-before-slice': 'x a [0:3]',
 'hash-in-word': 'x a#b',
 'hash-comment': 'x a #b',
 'include-glob': 'include /*.conf',
 'block-comment': 'server {\n  listen 80 # c\n}\n',
 'block-then-dir': 'x {} y',
 'brace-next-line': 'a\n{\n}',
 'stray-bracket': 'x ]\ny 1\n',
 'broken-block': 'server {\n  listen [80\n}\nnext 1\n',
 'bom': '﻿x 1',
 'crlf': 'x 1\r\ny 2',
 'lone-cr': 'x 1\ry',
 'unicode-str': 'x "é" # ü',
 'emoji-bare': 'x \U0001F600',
 'emoji-str': 'x "\U0001F600" y',
 'ip-port': 'x 127.0.0.1:3000',
 'colon-word': 'x color:hsl',
 'nul': 'x a\u0000}',
 'empty': '',
 'semis': ';;',
 'last-at-eof': 'x',
 'last-before-brace': 'a { b }',
 'unterminated': 'x "abc\ny 1\n',
}
for k, v in edge.items(): cases.append({'name': k, 'src': v})
json.dump(cases, open(os.path.join(here, 'cases.json'), 'w'), ensure_ascii=False, indent=0)
print(len(cases), 'cases')
