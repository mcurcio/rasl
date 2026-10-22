import { lex } from "/Volumes/Dock/Home/Code/rasl/.claude/worktrees/friendly-saha-6a52d1/js/packages/config/src/lexer.ts";
for (const s of ["x \u{1F600} y\n", "a\r\nb", "x \"é\" y"]) {
  console.log(JSON.stringify(s), lex(s).tokens.map(t => `${t.type}:${JSON.stringify(t.text)}@off${t.span.start.offset}/L${t.span.start.line}C${t.span.start.column}`).join("  "));
}
