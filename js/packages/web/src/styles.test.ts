import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

import { describe as group, expect, it } from "vitest";

// styles.css draws only with patchbay's tokens: every custom property it reads is one tokens.css defines, and it
// defines none of its own, so a renamed or removed token fails here rather than drawing nothing in the page.
const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
const tokens = readFileSync(createRequire(import.meta.url).resolve("@mcurcio/patchbay/tokens.css"), "utf8");
const defined = new Set([...tokens.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));

group("styles.css", () => {
  it("reads only custom properties that patchbay's tokens.css defines", () => {
    const read = [...new Set([...styles.matchAll(/var\(\s*(--[\w-]+)/g)].map((m) => m[1]))];
    expect(read.length).toBeGreaterThan(0);
    expect(read.filter((name) => !defined.has(name))).toEqual([]);
  });

  it("selects none of patchbay's own pb- classes, only the classes the editor gives its components", () => {
    expect([...styles.matchAll(/\.pb-[\w-]+/g)].map((m) => m[0])).toEqual([]);
  });

  it("defines no custom properties, React Flow's --xy-* included", () => {
    expect([...styles.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1])).toEqual([]);
  });
});
