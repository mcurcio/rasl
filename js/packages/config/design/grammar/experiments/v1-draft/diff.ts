import { readFileSync } from "node:fs";
import { parseDocument } from "/Volumes/Dock/Home/Code/rasl/.claude/worktrees/friendly-saha-6a52d1/js/packages/config/src/parser.ts";
import { serializeCst } from "/Volumes/Dock/Home/Code/rasl/.claude/worktrees/friendly-saha-6a52d1/js/packages/config/src/cst.ts";
const c = JSON.parse(readFileSync("lark/corpus.json", "utf8")) as { pos: string[]; mut: [string, boolean][] };
const ok = (s: string) => { const r = parseDocument(s); return { errs: r.errors, rt: serializeCst(r.cst) === s }; };
let posRej = 0, rtFail = 0; const posEx: string[] = []; const codes: Record<string, number> = {};
for (const s of c.pos) { const r = ok(s); if (!r.rt) rtFail++; if (r.errs.length) { posRej++; r.errs.forEach(e => codes[e.code] = (codes[e.code] ?? 0) + 1); if (posEx.length < 3) posEx.push(JSON.stringify(s).slice(0, 60)); } }
let fa = 0, fr = 0; const faEx: string[] = [];
for (const [s, refAcc] of c.mut) { const r = ok(s); if (!r.rt) rtFail++; const tsAcc = r.errs.length === 0; if (tsAcc && !refAcc) { fa++; if (faEx.length < 4) faEx.push(JSON.stringify(s).slice(0, 50)); } if (!tsAcc && refAcc) fr++; }
console.log(`positives ${c.pos.length}: TS reports errors on ${posRej}`, codes, posEx);
console.log(`mutants ${c.mut.length}: TS accepts but grammar rejects ${fa}; TS rejects but grammar accepts ${fr}`, faEx);
console.log(`round-trip failures: ${rtFail}`);
