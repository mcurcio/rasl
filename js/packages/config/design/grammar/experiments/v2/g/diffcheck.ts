// Differential check: REx-generated parser (oracle) vs mechanical Bison
// translation of the same file, on the normative token stream.
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { lexOracle, oracle } from "./oracle.ts";
const lines = readFileSync(process.argv[2], "utf8").trim().split("\n").map((l) => JSON.parse(l));
const bisonName = (k: string) => /^[A-Za-z]+$/.test(k) ? "K_" + k : "T_" + [...k].map((c) => /[A-Za-z0-9]/.test(c) ? c : "x" + c.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0")).join("");
let feed = "";
const results = lines.map(({ src, gen, kinds }) => {
  const toks = lexOracle(src).toks;
  // round trip: concatenating token texts must give the input back
  const cps = [...src];
  const rt = toks.map((t) => cps.slice(t.start, t.end).join("")).join("");
  feed += toks.map((t) => bisonName(t.kind)).join("\n") + (toks.length ? "\n" : "") + "K_EOF\n\n";
  const o = oracle(src);
  const realizable = gen && JSON.stringify(toks.map((t) => t.kind)) === JSON.stringify(kinds);
  return { src, gen, realizable, rt: rt === src, accept: o.cst !== null, code: o.first?.code ?? null, synErr: o.syntaxErrorAt };
});
const out = execFileSync("./bisoncheck", { input: feed }).toString().trim().split("\n");
let realizable = 0, realizableRejected = 0, errPosAgree = 0, errPosDisagree = 0, agree = 0, disagree = 0, rtFail = 0, genAccepted = 0, gens = 0, acc = 0, valueDiag = 0;
const codes: Record<string, number> = {};
results.forEach((r, i) => {
  const b = out[i];
  if (!r.rt) rtFail++;
  if (r.gen) { gens++; if (r.accept) genAccepted++; }
  if (r.accept) acc++;
  if (r.code) codes[r.code] = (codes[r.code] ?? 0) + 1;
  if (r.accept && r.code) valueDiag++;
  if (r.realizable) { realizable++; if (!r.accept) realizableRejected++; }
  if (!r.accept && b.startsWith("REJECT")) { if (Number(b.split(" ")[1]) === r.synErr) errPosAgree++; else { errPosDisagree++; if (errPosDisagree <= 5) console.log("ERRPOS", JSON.stringify(r.src), r.synErr, b); } }
  const bAccept = b === "ACCEPT";
  const same = bAccept === r.accept;
  if (same) agree++; else { disagree++; if (disagree <= 5) console.log("DISAGREE", JSON.stringify(r.src), "rex:", r.accept, "bison:", b); }
});
console.log({ realizable, realizableRejected, errPosAgree, errPosDisagree, inputs: results.length, agree, disagree, roundTripFailures: rtFail, generated: gens, generatedAccepted: genAccepted, accepted: acc, acceptedWithValueRuleDiag: valueDiag, firstDiagnosticCodes: codes });
