import { lex } from "/Volumes/Dock/Home/Code/rasl/.claude/worktrees/friendly-saha-6a52d1/js/packages/config/src/lexer.ts";
import { parseDocument } from "/Volumes/Dock/Home/Code/rasl/.claude/worktrees/friendly-saha-6a52d1/js/packages/config/src/parser.ts";
import { getDirectiveName, serializeRange } from "/Volumes/Dock/Home/Code/rasl/.claude/worktrees/friendly-saha-6a52d1/js/packages/config/src/cst.ts";
const show = (src: string) => {
  const r = lex(src);
  const toks = r.tokens.filter(t => !["whitespace","eof"].includes(t.type)).map(t => `${t.type}(${JSON.stringify(t.text)})`).join(" ");
  const p = parseDocument(src);
  const dirs = (ds: any[], d=0): string => ds.map(x => `${getDirectiveName(p.cst,x)}[${x.argRanges.map((a:any)=>serializeRange(p.cst,a)).join("|")}]${x.body?"{"+dirs(x.body,d+1)+"}":""}`).join(" ; ");
  console.log(JSON.stringify(src).padEnd(30), "=>", toks);
  console.log("".padEnd(30), "   CST:", dirs(p.cst.children), " diags:", [...p.errors, ...p.warnings].map(e=>`${e.code}@${e.span.start.offset}`).join(","));
};
for (const s of process.argv.slice(2)) show(s.replace(/\\n/g, "\n"));
