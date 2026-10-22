import { CharStream, CommonTokenStream } from "antlr4ng";
import { RaslLexer as L } from "../gen-ts/RaslLexer.js";
import { RaslParser as P } from "../gen-ts/RaslParser.js";
import { RaslRecovery } from "./recovery.js";
import { toCst } from "./cst.js";
export function parse(src: string) {
  const ts = new CommonTokenStream(new L(CharStream.fromString(src))); ts.fill();
  const p = new P(ts); p.removeErrorListeners(); const rec = new RaslRecovery(); p.errorHandler = rec;
  (p.interpreter as any).getSynValidOrSemInvalidAltThatFinishedDecisionEntryRule = () => 0;
  return { tokens: ts.getTokens(), tree: toCst(p.document()).tree, diags: rec.diags };
}
