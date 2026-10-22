// REx-generated TS parser on the shared corpus. Prints one normalized line per case.
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { config_ts as P } from "./config_ts.ts";
const CONCEPT: Record<string, string> = { Document: "document", Directive: "directive", LastDirective: "directive", Block: "block", SlicedWord: "slice", List: "list" };
const kind = (n: string) => n.replace(/^'(.*)'$/, "$1").replace("﻿", "Bom");
function norm(n: P.Symbol, out: string[], leaves: string[]): void {
  if (n instanceof P.Terminal) {
    if (n.name === "EOF") return;
    const t = (n as any).input?.substring?.(n.begin, n.end);
    leaves.push(t); out.push(kind(n.name) + JSON.stringify(t)); return;
  }
  const nt = n as P.Nonterminal; const c = CONCEPT[nt.name];
  if (c) out.push("(" + c);
  nt.children.forEach((k) => norm(k, out, leaves));
  if (c) out.push(")");
}
const cases = JSON.parse(readFileSync(process.argv[2], "utf8")) as { name: string; src: string }[];
for (const { name, src } of cases) {
  const b = new P.ParseTreeBuilder(); const p = new P.Parser(src, b);
  let line: string;
  try {
    p.parse_Document();
    const root = b.getStack()[0];
    const out: string[] = []; const leaves: string[] = [];
    // REx Terminal holds offsets only; read text from src
    (function fix(n: any) { if (n instanceof P.Terminal) (n as any).input = src; else n.children.forEach(fix); })(root);
    norm(root, out, leaves);
    const s = out.join(" ");
    line = "ACCEPT rt=" + (leaves.join("") === src) + " " + (s.length > 160 ? "sha:" + createHash("sha1").update(s).digest("hex").slice(0, 12) : s);
  } catch (e) {
    if (!(e instanceof P.ParseException)) throw e;
    line = "REJECT@" + [...src.slice(0, e.getBegin())].length;
  }
  console.log(name.padEnd(24), line);
}
