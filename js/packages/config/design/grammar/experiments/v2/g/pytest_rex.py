import sys; sys.path.insert(0, '.')
import config_py as P
for src in ['listen 80;', 'server {\n listen 80 # c\n}\n', 'x a[0:3] [1, b[2:]]', 'x "a""b"', 'x [:]', 'aé']:
    b = P.config_py.ParseTreeBuilder(); p = P.config_py(src, b)
    try:
        p.parse_Document(); print('ACCEPT', repr(src))
    except P.config_py.ParseException as e:
        print('REJECT', repr(src), 'at', e.getBegin())
