# Async include plan

## Goals

- Allow callers to provide an async resolver to load `include` targets.
- Maintain a clear boundary between parsing and I/O so the core parser stays deterministic.
- Surface diagnostics for missing files, circular includes, or resolver failures.
- Represent includes as a **document graph** so included files can be round-tripped back to their original sources.
- Support glob patterns in include paths (resolver-defined), while keeping deterministic include ordering.

## Proposed API additions

- Extend `IParseConfig` with:
  - `basePath?: string` – starting directory for relative include paths.
  - `sourceId?: string` – optional stable identity for the root document (used for diagnostics + graph edges).
  - `loader: (spec: string, ctx: { parentPath: string; depth: number }) => Promise<Array<{ source: string; resolvedPath: string }>>` – loads an include spec (path or glob) to one or more documents. Core code applies deterministic ordering.
  - `maxIncludeDepth?: number` – guard against cycles (default e.g. 16).
- Make `parse` async-only and require a `loader` always.

## Execution flow

1. Parse the parent file to a CST that still contains `include` directives.
2. Walk the CST/AST for `include` directives and use the `loader`:
   - `include` paths are **quoted string literals** and may be relative or absolute; interpretation (including globbing) is resolver-defined.
   - Resolve relative to `basePath` or the including file’s resolved path (when available).
   - Await the resolver; on failure, push a diagnostic and leave the include unresolved.
   - Sort matches ascending lexicographic by `resolvedPath`.
   - For each match:
     - parse the returned source via `parse` recursively (passing updated `parentPath` and incremented depth)
     - attach the parsed document (or null) as an include edge in the document graph (and to the directive facade if needed)
3. Track visited paths to prevent infinite recursion; emit a warning when the limit hits.
4. Keep the core result as a document graph; consumers can optionally build their own “single inlined document” view in a separate pass.

## Testing

- Mock resolver returning fixture strings to avoid real FS I/O in unit tests.
- Cover success path, missing file error, depth limit, and circular dependency cases.
- Cover glob: multiple matches, stable ordering, and “no matches” behavior.

## Open questions

- Should synchronous `parse` optionally accept a resolver that returns cached data immediately, or do we keep the split strict?
- Do we expose helper utilities for file-system based resolvers (e.g., Node `fs/promises` implementation) in this package or another module?
- Should include-resolution diagnostics use stable `code`s + 0-based line/column spans (recommended for cross-language parity)?
- Should “no glob matches” be an error or a warning (recommended: warning with a code)?
