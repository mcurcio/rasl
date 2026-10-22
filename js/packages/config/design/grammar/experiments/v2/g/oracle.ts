// Oracle prototype: normative tokens + CST + first diagnostic, computed only from
// REx parsers generated from config.ebnf plus the cst:/values: annotations read
// from that same file. No code from js/packages/config is used.
import { readFileSync } from "node:fs";
import { tokens as T } from "./tokens.ts";
import { lalr1 as P } from "./lalr1.ts";
import { values as V } from "./values.ts";

const SPEC = readFileSync(new URL("./config.ebnf", import.meta.url), "utf8");

// rule name -> spec concept, from "/* cst: kind */" annotations
const CONCEPT = new Map<string, string>();
{
  let last = "";
  for (const line of SPEC.split("\n")) {
    const m = /^([A-Za-z]+)\s*(::=)?/.exec(line);
    if (m) last = m[1];
    const c = /cst: ([a-z]+)/.exec(line);
    if (c && last) CONCEPT.set(last, c[1]);
  }
}

type Tok = { kind: string; start: number; end: number }; // code-point offsets
type Node = { kind: string; first: number; last: number; children: Node[] }; // token indices
type Diag = { code: string; start: number; end: number };

const TRIVIA = new Set(["Space", "Comment"]);
const kindOf = (rexName: string) =>
  rexName === "'﻿'" ? "Bom" : rexName.replace(/^'(.*)'$/, "$1");

function cpIndex(src: string): (u16: number) => number {
  const map = new Int32Array(src.length + 1);
  let cp = 0;
  for (let i = 0; i < src.length; i++) {
    map[i] = cp;
    const c = src.charCodeAt(i);
    if (c >= 0xd800 && c < 0xdc00 && i + 1 < src.length) {
      const d = src.charCodeAt(i + 1);
      if (d >= 0xdc00 && d < 0xe000) { map[++i] = cp; }
    }
    cp++;
  }
  map[src.length] = cp;
  return (u) => map[u];
}

class Collect implements T.BottomUpEventHandler {
  out: { name: string; b: number; e: number }[] = [];
  reset() {}
  nonterminal() {}
  terminal(name: string, b: number, e: number) { if (name !== "EOF") this.out.push({ name, b, e }); }
}

export function lexOracle(src: string): { toks: Tok[]; u16: { b: number; e: number }[] } {
  const c = new Collect();
  new T.Parser(src, c).parse_Tokens();
  const cp = cpIndex(src);
  return {
    toks: c.out.map((t) => ({ kind: kindOf(t.name), start: cp(t.b), end: cp(t.e) })),
    u16: c.out.map((t) => ({ b: t.b, e: t.e })),
  };
}

function holds(rule: string, text: string): boolean {
  try { new V.Parser(rule + text, new V.ParseTreeBuilder()).parse_Check(); return true; } catch { return false; }
}

export function oracle(src: string) {
  const { toks, u16 } = lexOracle(src);
  const at = new Map<number, number>(); // u16 begin -> token index
  u16.forEach((t, i) => at.set(t.b, i));
  const diags: Diag[] = [];

  // lexical diagnostics: one per error token
  toks.forEach((t) => {
    if (t.kind === "BadChar") diags.push({ code: "E1003", start: t.start, end: t.end });
    if (t.kind === "UnterminatedString") diags.push({ code: "E1001", start: t.start, end: t.end });
  });
  // value rule: escapes
  toks.forEach((t, i) => {
    if (t.kind !== "String") return;
    const text = src.slice(u16[i].b + 1, u16[i].e - 1);
    for (let k = 0; k < text.length; k++) {
      if (text[k] !== "\\") continue;
      if (!holds("EscapeText", text.slice(k, k + 2))) {
        diags.push({ code: "E1004", start: t.start + 1 + k, end: t.start + 3 + k });
      }
      k++;
    }
  });

  // syntax
  const b = new P.ParseTreeBuilder();
  const parser = new P.Parser(src, b);
  let cst: Node | null = null;
  let syntaxErrorAt = -1;
  try {
    parser.parse_Document();
    const root = b.getStack()[0] as P.Nonterminal;
    // REx's syntax parser lexes per parser state; it must agree with the
    // normative longest-match token stream on every accepted input.
    const seen: number[] = [];
    (function terms(n: P.Symbol) { if (n instanceof P.Terminal) { if (n.name !== "EOF") seen.push(n.begin, n.end); } else (n as P.Nonterminal).children.forEach(terms); })(root);
    const want = u16.flatMap((t) => [t.b, t.e]);
    if (seen.join() !== want.join()) throw new Error("TOKEN DISAGREEMENT " + seen.join() + " vs " + want.join());
    isTrivia = (i) => TRIVIA.has(toks[i].kind);
    cst = build(root, at)[0];
    // value rule: slice bounds
    walk(cst, (n) => {
      if (n.kind !== "slice") return;
      for (let i = n.first + 2; i < n.last; i++) {
        if (toks[i].kind === "Word" && !holds("IntegerText", src.slice(u16[i].b, u16[i].e))) {
          diags.push({ code: "E2007", start: toks[i].start, end: toks[i].end });
        }
      }
    });
  } catch (e) {
    if (!(e instanceof P.ParseException)) throw e;
    const idx = e.getBegin() >= src.length ? toks.length : at.get(e.getBegin());
    if (idx === undefined) throw new Error("ERROR OFFSET NOT AT A TOKEN BOUNDARY " + e.getBegin());
    syntaxErrorAt = idx;
    diags.push(syntaxDiag(toks, idx));
  }
  diags.sort((x, y) => x.start - y.start || (x.code < y.code ? -1 : 1));
  return { tokens: toks, cst, first: diags[0] ?? null, syntaxErrorAt };
}

let isTrivia: (i: number) => boolean = () => false;
function build(n: P.Symbol, at: Map<number, number>): Node[] {
  if (n instanceof P.Terminal) {
    if (n.name === "EOF") return [];
    const i = at.get(n.begin)!;
    return [{ kind: "#tok", first: i, last: i, children: [] }];
  }
  const nt = n as P.Nonterminal;
  const kids = nt.children.flatMap((c) => build(c, at));
  const concept = CONCEPT.get(nt.name);
  if (!concept) return kids; // grammar factoring is transparent
  // tight range: first..last token that is not Space/Comment; outer trivia belongs to the parent
  const sig = kids.filter((k) => k.kind !== "#tok" || !isTrivia(k.first));
  return [{
    kind: concept,
    first: concept === "document" ? 0 : sig.length ? sig[0].first : -1,
    last: concept === "document" ? Math.max(0, at.size - 1) : sig.length ? sig[sig.length - 1].last : -1,
    children: kids.filter((k) => k.kind !== "#tok"),
  }];
}

function walk(n: Node, f: (n: Node) => void) { f(n); n.children.forEach((c) => walk(c, f)); }

// First syntax diagnostic: a function of the offending token and the open
// concepts in the (viable) prefix before it, never of the parser's internals.
function syntaxDiag(toks: Tok[], idx: number): Diag {
  const tok = toks[idx];
  const span = tok ? { start: tok.start, end: tok.end } : { start: endOf(toks), end: endOf(toks) };
  if (tok && tok.kind === "BadChar") return { code: "E1003", ...span };
  if (tok && tok.kind === "UnterminatedString") return { code: "E1001", ...span };
  const open: { kind: string; i: number }[] = [];
  let prevSig = -1;
  for (let i = 0; i < idx; i++) {
    const k = toks[i].kind;
    if (TRIVIA.has(k)) continue;
    if (k === "{") open.push({ kind: "block", i });
    if (k === "[") open.push({ kind: i > 0 && toks[i - 1].kind === "Word" ? "slice" : "list", i });
    if (k === "}" || k === "]") open.pop();
    prevSig = i;
  }
  const top = open[open.length - 1];
  const atStatementStart = prevSig < 0 || ["Newline", ";", "{", "}"].includes(toks[prevSig].kind) && top?.kind !== "list";
  const opener = (o: { i: number }) => ({ start: toks[o.i].start, end: toks[o.i].end });
  if (top?.kind === "slice") return { code: "E2007", ...opener(top) };
  if (!tok && top?.kind === "list") return { code: "E2004", ...opener(top) };
  if (!tok && top?.kind === "block") return { code: "E2003", ...opener(top) };
  if (tok?.kind === "]" && top?.kind !== "list") return { code: "E2004", ...span };
  if (tok?.kind === "{" && atStatementStart) return { code: "E2008", ...span };
  if (atStatementStart && tok?.kind !== "Word") return { code: "E2002", ...span };
  if (top?.kind === "list") return { code: "E2004", ...span };
  return { code: "E2005", ...span };
}
const endOf = (toks: Tok[]) => (toks.length ? toks[toks.length - 1].end : 0);

// CLI: print one JSON line per argument (\n escapes allowed)
if (import.meta.main) {
  for (const arg of process.argv.slice(2)) {
    const src = arg.replace(/\\n/g, "\n").replace(/\\r/g, "\r").replace(/\\u\{([0-9a-f]+)\}/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)));
    const r = oracle(src);
    const toks = r.tokens.filter((t) => t.kind !== "Space").map((t) => `${t.kind}(${JSON.stringify([...src].slice(t.start, t.end).join(""))})`).join(" ");
    const show = (n: Node | null): string => !n ? "-" : n.kind + "[" + n.first + ".." + n.last + "]" + (n.children.length ? "(" + n.children.map(show).join(" ") + ")" : "");
    console.log(JSON.stringify(src).padEnd(26), toks);
    console.log("".padEnd(26), "cst:", show(r.cst), " first:", r.first ? `${r.first.code}@${r.first.start}` : "none");
  }
}
