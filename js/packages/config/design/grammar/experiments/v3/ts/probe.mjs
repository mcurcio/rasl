import { Parser, Language } from "web-tree-sitter";
await Parser.init();
const p = new Parser(); p.setLanguage(await Language.load(new URL("./rasl/rasl.wasm", import.meta.url).pathname));
for (const src of ["﻿x 1", "server {\n  listen [80\n}\nnext 1\n", "x ]\ny 1\n", "a {\n  b [1\n  c 2\n}\nd 3\n", "x a[:]\ny 1\n"]) {
  const t = p.parse(src);
  console.log(JSON.stringify(src), "root", t.rootNode.startIndex, "-", t.rootNode.endIndex);
  console.log("   ", t.rootNode.toString());
}
