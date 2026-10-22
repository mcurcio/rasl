// Driver: corpus -> REx-comparable lines (stdout) and canonical CST JSON lines (argv[3]).
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { CharStream, CommonTokenStream, BaseErrorListener, PredictionMode } from "antlr4ng";
import { RaslLexer as L } from "../gen-ts/RaslLexer.js";
import { RaslParser as P } from "../gen-ts/RaslParser.js";
import { RaslRecovery } from "./recovery.js";
import { toCst, Node } from "./cst.js";

const LEAF: Record<string, string> = { WORD: "Word", STRING: "String", SPACE: "Space", COMMENT: "Comment", NEWLINE: "Newline", BOM: "Bom" };
class Count extends BaseErrorListener { n = 0; syntaxError() { this.n++; } }
const canon = (v: unknown) => JSON.stringify(v).replace(/[\u0080-￿]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
const cases = JSON.parse(readFileSync(process.argv[2], "utf8")) as { name: string; src: string }[];
const jl: string[] = []; let lexErrs = 0;
for (const { name, src } of cases) {
  const lexer = new L(CharStream.fromString(src)); const lc = new Count();
  lexer.removeErrorListeners(); lexer.addErrorListener(lc);
  const ts = new CommonTokenStream(lexer); ts.fill();
  const parser = new P(ts); parser.removeErrorListeners();
  const rec = new RaslRecovery(); parser.errorHandler = rec;
  if (process.env.SLL) (parser.interpreter as any).predictionMode = PredictionMode.SLL;
  if (process.env.NOHEUR) (parser.interpreter as any).getSynValidOrSemInvalidAltThatFinishedDecisionEntryRule = () => 0;
  let crash = "";
  let tree: Node = ["document", 0, 0, []], seen: number[] = [];
  try { ({ tree, seen } = toCst(parser.document())); } catch (e: any) { crash = String(e?.constructor?.name ?? e); }
  lexErrs += lc.n;
  const toks = ts.getTokens().filter((t: any) => t.type !== -1);
  const tokens = toks.map((t: any) => [P.symbolicNames[t.type], t.text]);
  const rt = tokens.map((t: any) => t[1]).join("") === src;
  const cover = seen.length === toks.length && seen.every((x, i) => x === i);
  jl.push(canon({ name, tokens, tree, diags: rec.diags, rt, cover, crash }));
  if (rec.diags.length || crash) { console.log(name.padEnd(24), "REJECT@" + (rec.diags[0]?.offset ?? "CRASH")); continue; }
  const out: string[] = [];
  (function sx(n: Node) {
    out.push("(" + n[0]); let i = n[1];
    for (const k of [...n[3], null]) {
      const stop = k ? k[1] : n[2];
      for (; i < stop; i++) { const t = toks[i]; out.push((LEAF[P.symbolicNames[t.type]] ?? t.text) + JSON.stringify(t.text)); }
      if (k) { sx(k); i = k[2]; }
    }
    out.push(")");
  })(tree);
  const s = out.join(" ");
  console.log(name.padEnd(24), "ACCEPT rt=" + rt + " " + (s.length > 160 ? "sha:" + createHash("sha1").update(s).digest("hex").slice(0, 12) : s));
}
writeFileSync(process.argv[3], jl.join("\n") + "\n");
console.error("lexer errors:", lexErrs);
