# rasl-bzv.1 recovery for the ANTLR4-generated parser: line-level resync, no conjured tokens.
from antlr4 import Token
from antlr4.error.ErrorStrategy import DefaultErrorStrategy
from antlr4.error.Errors import InputMismatchException
from RaslParser import RaslParser as P

def rule_of(c): return c.getRuleIndex() if c is not None and hasattr(c, 'getRuleIndex') else None
def is_statements(c): return rule_of(c) == P.RULE_statements

def stmt_start(s, cur):
    """Start token index of the statement being parsed in statements context s (or cur)."""
    kids = [k for k in (s.children or [] if s else []) if rule_of(k) in (P.RULE_directive, P.RULE_lastDirective)]
    return kids[-1].start.tokenIndex if kids else cur

def scope(p):
    """The statements context the error belongs to, and whether it sits inside a block."""
    c = p._ctx
    if rule_of(c) in (P.RULE_block, P.RULE_document):
        return next((k for k in reversed(c.children or []) if is_statements(k)), None), rule_of(c) == P.RULE_block
    while c is not None and not is_statements(c): c = c.parentCtx
    q = c
    while q is not None and is_statements(q.parentCtx): q = q.parentCtx       # re-entered statements nest
    return c, rule_of(q.parentCtx if q is not None else None) == P.RULE_block

def depth(p, frm, to):
    """Bracket stack (True = slice bracket) and brace depth over tokens [frm, to)."""
    br, cd = [], 0
    for i in range(frm, to):
        t = p._input.get(i).type
        if t == P.LBRACK: br.append(i > 0 and p._input.get(i - 1).type == P.WORD)
        elif t == P.RBRACK:
            if br: br.pop()
        elif t == P.LBRACE: cd += 1
        elif t == P.RBRACE and cd > 0: cd -= 1
    return br, cd

class RaslRecovery(DefaultErrorStrategy):
    def __init__(self):
        super().__init__(); self.diags = []
    def sync(self, p): pass                                  # errors surface at prediction or match
    def recoverInline(self, p): raise InputMismatchException(p)   # never conjure a token
    def reportError(self, p, e):
        if self.inErrorRecoveryMode(p): return
        self.beginErrorCondition(p)
        t = e.offendingToken or p.getCurrentToken()
        s, in_block = scope(p)
        br, cd = depth(p, stmt_start(s, p._input.index), t.tokenIndex)
        prev = t.tokenIndex - 1
        while prev >= 0 and p._input.get(prev).type in (P.SPACE, P.COMMENT): prev -= 1
        if t.type == P.BAD_CHAR or (t.type == P.BOM and t.tokenIndex > 0): code = 'E1003'
        elif t.type == P.UNTERMINATED_STRING: code = 'E1001'
        elif br and br[-1]: code = 'E2007'
        elif t.type == P.RBRACK or (br and t.type in (P.RBRACE, Token.EOF)): code = 'E2004'
        elif t.type == P.LBRACE and (prev < 0 or p._input.get(prev).type == P.NEWLINE): code = 'E2008'
        elif t.type == Token.EOF and (in_block or cd > 0): code = 'E2003'
        else: code = 'E2001'
        end = t.start if t.type == Token.EOF else t.stop + 1
        self.diags.append({'code': code, 'offset': t.start, 'end': end, 'line': t.line - 1, 'column': t.column})
    def skip(self, p):
        """Consume to the end of the bad statement: ';' or newline outside brackets and braces, a whole
        nested block, or stop before the '}' that closes the enclosing block, or EOF."""
        s, in_block = scope(p)
        cur = p._input.index
        br, cd = depth(p, stmt_start(s, cur), cur)
        bd = len(br)
        while True:
            t = p._input.LA(1)
            if t == Token.EOF: return
            if t == P.RBRACE and cd == 0:
                if in_block: return
                p.consume(); continue
            p.consume()
            if t == P.LBRACK: bd += 1
            elif t == P.RBRACK: bd = max(0, bd - 1)
            elif t == P.LBRACE: cd += 1
            elif t == P.RBRACE: cd -= 1
            if (t == P.RBRACE and cd == 0 and bd == 0) or (t in (P.NEWLINE, P.SEMI) and bd == 0 and cd == 0):
                return self.endErrorCondition(p)            # statement ended: the next error gets reported
    def junk(self, p):
        """statements() can return early at a bad token without raising: report it (no-op while recovering)."""
        self.reportError(p, InputMismatchException(p))
    def recover(self, p, e):
        r, la = rule_of(p._ctx), lambda: p._input.LA(1)
        if is_statements(p._ctx):
            self.skip(p)
            if la() not in (Token.EOF, P.RBRACE): p.statements()
        elif r == P.RULE_document:
            while la() != Token.EOF:
                self.junk(p); self.skip(p)
                if la() != Token.EOF: p.statements()
        elif r == P.RULE_block and la() != Token.EOF:
            while la() not in (Token.EOF, P.RBRACE):
                self.junk(p); self.skip(p)
                if la() not in (Token.EOF, P.RBRACE): p.statements()
            p.match(P.RBRACE)                                # raises at EOF: unwinds as an unclosed block
        else:
            raise e                                          # unwind to the nearest recovery point
