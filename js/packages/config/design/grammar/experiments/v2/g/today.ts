import { readFileSync } from "node:fs";
import { parseDocument } from "/Volumes/Dock/Home/Code/rasl/.claude/worktrees/friendly-saha-6a52d1/js/packages/config/src/parser.ts";
import { serializeCst } from "/Volumes/Dock/Home/Code/rasl/.claude/worktrees/friendly-saha-6a52d1/js/packages/config/src/cst.ts";
import { oracle } from "./oracle.ts";
const lines = readFileSync(process.argv[2], "utf8").trim().split("\n").map((l) => JSON.parse(l));
let both = 0, neither = 0, todayOnly = 0, specOnly = 0, rt = 0; const ex: Record<string, string[]> = { todayOnly: [], specOnly: [] };
for (const { src } of lines) {
  const p = parseDocument(src); const t = p.errors.length === 0; const s = oracle(src).cst !== null && !oracle(src).first;
  if (serializeCst(p.cst) !== src) rt++;
  if (t && s) both++; else if (!t && !s) neither++; else if (t) { todayOnly++; ex.todayOnly.length < 6 && ex.todayOnly.push(src); } else { specOnly++; ex.specOnly.length < 6 && ex.specOnly.push(src); }
}
console.log({ inputs: lines.length, bothAccept: both, bothReject: neither, acceptedOnlyToday: todayOnly, acceptedOnlyBySpec: specOnly, todayRoundTripFailures: rt });
console.log(JSON.stringify(ex, null, 1));
