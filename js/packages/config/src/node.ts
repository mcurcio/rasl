import { readdir, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";

import type { DocumentLoader, DocumentWriter } from "./io.js";

const hasGlob = (spec: string): boolean => /[*?]/.test(spec);

const globToRegExp = (pattern: string): RegExp => {
  const escaped = pattern.replace(/[.+^${}()|\\]/g, "\\$&");
  const withStars = escaped.replace(/\*/g, ".*").replace(/\?/g, ".");
  return new RegExp(`^${withStars}$`);
};

/**
 * Create a filesystem-backed document loader for Node.js.
 *
 * - Resolves includes relative to `dirname(ctx.parentPath)`
 * - Supports `*` and `?` globs within a directory
 */
export function createFsLoader(): DocumentLoader {
  return async (spec, ctx) => {
    const baseDir = dirname(ctx.parentPath);
    const fullSpec = resolve(baseDir, spec);

    if (!hasGlob(spec)) {
      const source = await readFile(fullSpec, "utf-8");
      return [{ source, resolvedPath: fullSpec }];
    }

    const dir = dirname(fullSpec);
    const pattern = basename(fullSpec);
    const re = globToRegExp(pattern);

    const entries = await readdir(dir, { withFileTypes: true });
    const matches = entries
      .filter((e) => e.isFile() && re.test(e.name))
      .map((e) => resolve(dir, e.name))
      .sort((a, b) => a.localeCompare(b));

    const out: Array<{ source: string; resolvedPath: string }> = [];
    for (const p of matches) {
      out.push({ source: await readFile(p, "utf-8"), resolvedPath: p });
    }
    return out;
  };
}

/**
 * Create a filesystem-backed document writer for Node.js.
 */
export function createFsWriter(): DocumentWriter {
  return {
    async write(resolvedPath, source) {
      await writeFile(resolvedPath, source, "utf-8");
    },
  };
}
