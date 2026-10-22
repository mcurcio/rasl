// tree-sitter (web-tree-sitter, wasm) on the shared corpus; same normalized output as rex/run_ts.ts.
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { Parser, Language } from "web-tree-sitter";
await Parser.init();
const lang = await Language.load(new URL("./rasl/rasl.wasm", import.meta.url).pathname);
const parser = new Parser(); parser.setLanguage(lang);
const CONCEPT = new Set(["document", "directive", "block", "slice", "list"]);
const LEAF = { word: "Word", string: "String", space: "Space", comment: "Comment", newline: "Newline", bom: "Bom" };
const enc = new TextEncoder(), dec = new TextDecoder();
const cases = JSON.parse(readFileSync(process.argv[2], "utf8"));
const mode = process.argv[3] ?? "norm";
for (const { name, src } of cases) {
  const tree = parser.parse(src);
  const cp = (u16) => [...src.slice(0, u16)].length; // web-tree-sitter indexes UTF-16 code units
  const root = tree.rootNode;
  if (mode === "sexp") { console.log(name.padEnd(24), root.toString()); continue; }
  if (root.hasError) {
    let first = null;
    (function find(n) { if (first) return; if (n.isError || n.isMissing) { first = n; return; } for (const c of n.children) find(c); })(root);
    console.log(name.padEnd(24), "REJECT@" + (first ? cp(first.startIndex) : "?") + (first?.isMissing ? " (MISSING " + first.type + ")" : ""));
    continue;
  }
  const out = [], leaves = []; let pos = root.startIndex, gaps = false;
  if (pos === 1 && src[0] === "\ufeff") { leaves.push(src[0]); }
  (function walk(n) {
    if (CONCEPT.has(n.type)) out.push("(" + n.type);
    if (n.type === "document" && leaves.length === 1) out.push("Bom" + JSON.stringify(leaves[0]));
    if (!CONCEPT.has(n.type) && (n.childCount === 0 || LEAF[n.type])) {
      if (n.startIndex !== pos) gaps = true; pos = n.endIndex;
      leaves.push(n.text); out.push((LEAF[n.type] ?? n.type) + JSON.stringify(n.text)); return;
    }
    for (const c of n.children) walk(c);
    if (CONCEPT.has(n.type)) out.push(")");
  })(root);
  if (pos !== src.length) gaps = true;
  const s = out.join(" ");
  console.log(name.padEnd(24), "ACCEPT rt=" + (leaves.join("") === src && !gaps) + " " + (s.length > 160 ? "sha:" + createHash("sha1").update(s).digest("hex").slice(0, 12) : s));
}
