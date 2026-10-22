// ANTLR4 TypeScript target on the shared corpus; same normalized output as rex/run_ts.ts.
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { CharStreams, CommonTokenStream, ErrorListener, ParserRuleContext, TerminalNode } from "antlr4";
import RaslLexer from "./gen-ts/RaslLexer.js";
import RaslParser from "./gen-ts/RaslParser.js";
const CONCEPT: Record<string, string> = { document: "document", directive: "directive", lastDirective: "directive", block: "block", slicedWord: "slice", list: "list" };
const LEAF: Record<string, string> = { WORD: "Word", STRING: "String", SPACE: "Space", COMMENT: "Comment", NEWLINE: "Newline", BOM: "Bom" };
class First extends ErrorListener<any> { at = -1; msgs: string[] = [];
  syntaxError(_r: any, tok: any, line: number, col: number, msg: string) { if (this.at < 0) this.at = tok ? tok.start : -2; this.msgs.push(`${line}:${col} ${msg}`); } }
const cases = JSON.parse(readFileSync(process.argv[2], "utf8")) as { name: string; src: string }[];
const verbose = process.argv[3] === "-v";
for (const { name, src } of cases) {
  const lexer = new RaslLexer(CharStreams.fromString(src));
  const parser = new RaslParser(new CommonTokenStream(lexer));
  const err = new First(); parser.removeErrorListeners(); parser.addErrorListener(err);
  lexer.removeErrorListeners();
  const tree = parser.document();
  if (err.at !== -1) { console.log(name.padEnd(24), "REJECT@" + err.at + (verbose ? "  " + err.msgs.join(" | ") + "\n    tree: " + tree.toStringTree(parser.ruleNames, parser) : "")); continue; }
  const out: string[] = [], leaves: string[] = [];
  (function walk(n: any) {
    if (n instanceof TerminalNode) {
      const t = n.symbol; if (t.type === -1) return;
      const sym = RaslParser.symbolicNames[t.type] ?? ""; leaves.push(t.text);
      out.push((LEAF[sym] ?? t.text) + JSON.stringify(t.text)); return;
    }
    const rn = parser.ruleNames[(n as ParserRuleContext).ruleIndex]; const c = CONCEPT[rn];
    if (c) out.push("(" + c);
    for (const k of (n as ParserRuleContext).children ?? []) walk(k);
    if (c) out.push(")");
  })(tree);
  const s = out.join(" ");
  console.log(name.padEnd(24), "ACCEPT rt=" + (leaves.join("") === src) + " " + (s.length > 160 ? "sha:" + createHash("sha1").update(s).digest("hex").slice(0, 12) : s));
}
