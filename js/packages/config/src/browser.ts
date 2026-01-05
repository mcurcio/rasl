import type { DocumentLoader, DocumentWriter } from "./io.js";

/**
 * Create a fetch-backed document loader for browser-like environments.
 *
 * Notes:
 * - `ctx.parentPath` and `resolvedPath` are treated as URL strings.
 * - Globs are not supported (a loader cannot enumerate directories via fetch).
 */
export function createFetchLoader(fetchImpl: typeof fetch): DocumentLoader {
  return async (spec, ctx) => {
    if (/[*?]/.test(spec)) return [];

    const url = new URL(spec, ctx.parentPath).toString();
    const res = await fetchImpl(url);
    if (!res.ok) return [];
    return [{ source: await res.text(), resolvedPath: url }];
  };
}

/**
 * Create a fetch-backed document writer for browser-like environments.
 *
 * Uses `PUT` by default and writes `text/plain` bodies.
 */
export function createFetchWriter(
  fetchImpl: typeof fetch,
  options?: { method?: string; contentType?: string },
): DocumentWriter {
  const method = options?.method ?? "PUT";
  const contentType = options?.contentType ?? "text/plain";

  return {
    async write(resolvedPath, source) {
      await fetchImpl(resolvedPath, {
        method,
        headers: { "content-type": contentType },
        body: source,
      });
    },
  };
}
