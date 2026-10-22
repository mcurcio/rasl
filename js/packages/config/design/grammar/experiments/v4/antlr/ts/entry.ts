import { CharStreams, CommonTokenStream } from "antlr4";
import L from "../gen-ts/RaslLexer.js";
import P from "../gen-ts/RaslParser.js";
import { RaslRecovery } from "./recovery.js";
import { toCst } from "./cst.js";
export function parse(src: string) {
  const ts = new CommonTokenStream(new L(CharStreams.fromString(src))); ts.fill();
  const p = new P(ts); p.removeErrorListeners(); const rec = new RaslRecovery(); p._errHandler = rec;
  (p._interp as any).getSynValidOrSemInvalidAltThatFinishedDecisionEntryRule = () => 0;
  return { tokens: (ts as any).tokens, tree: toCst(p.document()).tree, diags: rec.diags };
}
