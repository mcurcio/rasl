import { readFileSync } from "node:fs";
import { oracle } from "./oracle.ts";
const root = "/Volumes/Dock/Home/Code/rasl/.claude/worktrees/friendly-saha-6a52d1/";
for (const f of ["hyperhdr.conf", "family_room.conf", "virtual.conf", "js/external-test.conf", "js/test.conf"]) {
  const src = readFileSync(root + f, "utf8"); const r = oracle(src);
  const cps = [...src]; const rt = r.tokens.map((t) => cps.slice(t.start, t.end).join("")).join("") === src;
  const count = (n: any, k: string): number => !n ? 0 : (n.kind === k ? 1 : 0) + n.children.reduce((a: number, c: any) => a + count(c, k), 0);
  const ctx = r.first ? JSON.stringify(cps.slice(Math.max(0, r.first.start - 25), r.first.end + 10).join("")) : "";
  console.log(f.padEnd(22), "bytes", String(src.length).padStart(5), "roundTrip", rt, "directives", count(r.cst, "directive"), "slices", count(r.cst, "slice"), "lists", count(r.cst, "list"), "first", r.first?.code ?? "none", ctx);
}
