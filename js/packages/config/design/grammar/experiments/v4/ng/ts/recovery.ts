// rasl-bzv.1 recovery for the ANTLR4-generated parser: line-level resync, no conjured tokens.
import { DefaultErrorStrategy, InputMismatchException, Parser, RecognitionException, Token } from "antlr4ng";
import { RaslParser as P } from "../gen-ts/RaslParser.js";

export interface Diag { code: string; offset: number; end: number; line: number; column: number }

const ruleOf = (c: any) => c?.ruleIndex;
const isStatements = (c: any) => ruleOf(c) === P.RULE_statements;

/** Start token index of the statement being parsed in statements context s (or `cur`). */
function stmtStart(p: any, s: any, cur: number): number {
  const kids = (s?.children ?? []).filter((k: any) => ruleOf(k) === P.RULE_directive || ruleOf(k) === P.RULE_lastDirective);
  return kids.length ? kids[kids.length - 1].start.tokenIndex : cur;
}
/** The statements context the error belongs to, and whether it sits inside a block. */
function scope(p: any): { s: any; inBlock: boolean } {
  let c = p.context;
  if (ruleOf(c) === P.RULE_block || ruleOf(c) === P.RULE_document)
    return { s: [...(c.children ?? [])].reverse().find(isStatements), inBlock: ruleOf(c) === P.RULE_block };
  while (c && !isStatements(c)) c = c.parent;
  let q = c; while (isStatements(q?.parent)) q = q.parent;       // re-entered statements nest
  return { s: c, inBlock: ruleOf(q?.parent) === P.RULE_block };
}
/** Bracket stack (true = slice bracket) and brace depth over tokens [from, to). */
function depth(p: any, from: number, to: number) {
  const br: boolean[] = []; let cd = 0;
  for (let i = from; i < to; i++) {
    const t = p.tokenStream.get(i).type;
    if (t === P.LBRACK) br.push(i > 0 && p.tokenStream.get(i - 1).type === P.WORD);
    else if (t === P.RBRACK) br.pop();
    else if (t === P.LBRACE) cd++;
    else if (t === P.RBRACE && cd > 0) cd--;
  }
  return { br, cd };
}

export class RaslRecovery extends DefaultErrorStrategy {
  diags: Diag[] = [];
  sync(_p: Parser) {}                                     // errors surface at prediction or match
  recoverInline(p: Parser): Token { throw new InputMismatchException(p); }   // never conjure a token
  reportError(p: any, e: RecognitionException) {
    if (this.inErrorRecoveryMode(p)) return;
    this.beginErrorCondition(p);
    const t: any = (e as any).offendingToken ?? p.getCurrentToken();
    const { s, inBlock } = scope(p);
    const { br, cd } = depth(p, stmtStart(p, s, p.tokenStream.index), t.tokenIndex);
    let prev = t.tokenIndex - 1;
    while (prev >= 0 && [P.SPACE, P.COMMENT].includes(p.tokenStream.get(prev).type)) prev--;
    const code =
      t.type === P.BAD_CHAR || (t.type === P.BOM && t.tokenIndex > 0) ? "E1003"
      : t.type === P.UNTERMINATED_STRING ? "E1001"
      : br.length && br[br.length - 1] ? "E2007"
      : t.type === P.RBRACK || (br.length && (t.type === P.RBRACE || t.type === Token.EOF)) ? "E2004"
      : t.type === P.LBRACE && (prev < 0 || p.tokenStream.get(prev).type === P.NEWLINE) ? "E2008"
      : t.type === Token.EOF && (inBlock || cd > 0) ? "E2003"
      : "E2001";
    const end = t.type === Token.EOF ? t.start : t.stop + 1;
    this.diags.push({ code, offset: t.start, end, line: t.line - 1, column: t.column });
  }
  /** Consume to the end of the bad statement: ';' or newline outside brackets and braces, a whole
   *  nested block, or stop before the '}' that closes the enclosing block, or EOF. */
  private skip(p: any) {
    const { s, inBlock } = scope(p);
    const cur = p.tokenStream.index;
    let { br, cd } = depth(p, stmtStart(p, s, cur), cur);
    let bd = br.length;
    for (;;) {
      const t = p.tokenStream.LA(1);
      if (t === Token.EOF) return;
      if (t === P.RBRACE && cd === 0) { if (inBlock) return; p.consume(); continue; }
      p.consume();
      if (t === P.LBRACK) bd++;
      else if (t === P.RBRACK) bd = Math.max(0, bd - 1);
      else if (t === P.LBRACE) cd++;
      else if ((t === P.RBRACE && --cd === 0 && bd === 0) || ((t === P.NEWLINE || t === P.SEMI) && bd === 0 && cd === 0))
        return this.endErrorCondition(p);                // statement ended: the next error gets reported
    }
  }
  /** statements() can return early at a bad token without throwing: report it (no-op while recovering). */
  private junk(p: any) { this.reportError(p, new InputMismatchException(p)); }
  recover(p: any, e: RecognitionException) {
    const r = ruleOf(p.context), la = () => p.tokenStream.LA(1);
    if (isStatements(p.context)) {
      this.skip(p);
      if (la() !== Token.EOF && la() !== P.RBRACE) p.statements();
    } else if (r === P.RULE_document) {
      while (la() !== Token.EOF) { this.junk(p); this.skip(p); if (la() !== Token.EOF) p.statements(); }
    } else if (r === P.RULE_block && la() !== Token.EOF) {
      while (la() !== Token.EOF && la() !== P.RBRACE) { this.junk(p); this.skip(p); if (la() !== Token.EOF && la() !== P.RBRACE) p.statements(); }
      p.match(P.RBRACE);                                  // throws at EOF: unwinds as an unclosed block
    } else throw e;                                       // unwind to the nearest recovery point
  }
}
