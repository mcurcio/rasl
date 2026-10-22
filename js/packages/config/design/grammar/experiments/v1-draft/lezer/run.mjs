import { parser } from "./good2.js";
import { readFileSync } from "node:fs";
const strict = parser.configure({ strict: true });
const root = "/Volumes/Dock/Home/Code/rasl/.claude/worktrees/friendly-saha-6a52d1/";
const verdict = (s) => { try { strict.parse(s); return "ACCEPT"; } catch (e) { return "REJECT " + e.message.split("\n")[0].slice(0, 40); } };
for (const f of ["hyperhdr.conf","family_room.conf","virtual.conf","js/test.conf","js/external-test.conf"]) console.log(verdict(readFileSync(root+f,"utf8")), f);
for (const c of ["connect a[0:3]","connect a[:3]","connect a[:]","connect a[1]","x //c","x /a","x a//b","a b c","x [1;2]","x [1, 2,]","a\n{\n}","color #fff","x a#b"])
  console.log("  ", JSON.stringify(c).padEnd(20), verdict(c));
const t = parser.parse("graph {\n  node C x { connect a[0:3]; }\n}\n");
let out = []; t.iterate({ enter: n => { out.push(n.name); } }); console.log("tree node kinds:", [...new Set(out)].join(" "));
