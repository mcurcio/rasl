import type { ISourceSpan } from "./tokens.js";

/**
 * Loader context for resolving includes.
 */
export interface ILoadContext {
  /** Identity of the including document (resolvedPath). */
  parentPath: string;
  /** Current include depth. */
  depth: number;
}

/**
 * Loaded document.
 */
export interface ILoadedDocument {
  /** Document source text content. */
  source: string;
  /** Stable identity for the loaded document (file path, URL, etc). */
  resolvedPath: string;
}

/**
 * Document loader.
 *
 * Returns zero or more resolved documents. Returning an empty array means
 * "no matches", which is treated as a fatal include error by `parse()`.
 */
export type DocumentLoader = (spec: string, ctx: ILoadContext) => Promise<ILoadedDocument[]>;

/**
 * Document writer.
 */
export interface DocumentWriter {
  write(resolvedPath: string, source: string): Promise<void>;
}

/**
 * Combine multiple loaders.
 *
 * For non-glob includes (single matches), loaders are tried in order and the
 * first non-empty result is used.
 *
 * For glob-style includes, results are concatenated across loaders and
 * de-duplicated by `resolvedPath`.
 */
export function composeLoaders(loaders: readonly DocumentLoader[]): DocumentLoader {
  const hasGlob = (spec: string): boolean => /[*?]/.test(spec);

  return async (spec, ctx) => {
    if (!hasGlob(spec)) {
      for (const loader of loaders) {
        const out = await loader(spec, ctx);
        if (out.length > 0) return out;
      }
      return [];
    }

    const byPath = new Map<string, ILoadedDocument>();
    for (const loader of loaders) {
      const out = await loader(spec, ctx);
      for (const doc of out) {
        byPath.set(doc.resolvedPath, doc);
      }
    }
    return [...byPath.values()];
  };
}

/**
 * Create a synthetic span for graph-level errors when a specific location is
 * not available.
 */
export function syntheticSpan(): ISourceSpan {
  return {
    start: { offset: 0, line: 0, column: 0 },
    end: { offset: 0, line: 0, column: 0 },
  };
}
