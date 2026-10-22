const mods = process.argv.slice(2);
const cases = ["x //c","x /","x /a//b","x a//b","include /*.conf;","include /etc/*.conf;","a /*\n*/ b","a /* x */ b","x 'str'","x :3","x [:3]","x [0:3]","x a[0:3]","x a[1]","x a[:]","x a[1,2]","x a [1]","x \"a\"#c","x a#b","x #c","x\r\ny","x\ry","x \"a\\qb\"","a { b } c","a {} b {}","a {\n}\n","x [\n1,\n2,\n]","x [1 2]","x -1.5e3","x \"a\"\"b\"","x \"a\"b","x a\"b\"","x a'b'","x [a][b]","x a[0:3][1:2]", "x  y", "x a b"];
for (const m of mods) {
  const { parser } = await import("./" + m);
  const strict = parser.configure({ strict: true });
  console.log("=== " + m);
  for (const c of cases) {
    let v;
    try { const t = strict.parse(c); const out=[]; t.iterate({enter:n=>{ if(n.name!=="Document") out.push(n.name+(n.type.isTop?"":"")+(["Word","String","LineComment","BlockComment"].includes(n.name)?"("+JSON.stringify(c.slice(n.from,n.to))+")":"")); }}); v = "ACCEPT " + out.join(" "); }
    catch (e) { v = "REJECT " + e.message.split("\n")[0].slice(0, 50); }
    console.log("  ", JSON.stringify(c).padEnd(26), v);
  }
}
