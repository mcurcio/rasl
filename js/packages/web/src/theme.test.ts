import { readFileSync } from "node:fs";

import { themeScript } from "@mcurcio/patchbay/hooks";
import { describe as group, expect, it } from "vitest";

import { THEME_KEY } from "./theme";

// The theme's first paint: index.html inlines patchbay's themeScript for the key useTheme keeps the choice under, before
// the page's module, so a kept dark choice never flashes light.
const indexHtml = readFileSync(new URL("../index.html", import.meta.url), "utf8");

group("the theme's first paint", () => {
  it("inlines patchbay's themeScript for rasl's key in index.html, before the page's module", () => {
    const script = themeScript(THEME_KEY);
    const inline = /<script>([\s\S]*?)<\/script>/.exec(indexHtml);
    expect(inline?.[1]).toBe(script);
    expect(indexHtml.indexOf(script)).toBeLessThan(indexHtml.indexOf('<script type="module"'));
  });
});
