# Async include plan

## Goals
- Allow callers to provide an async resolver to load `include` targets.
- Maintain a clear boundary between parsing and I/O so the core parser stays deterministic.
- Surface diagnostics for missing files, circular includes, or resolver failures.

## Proposed API additions
- Extend `IParseConfig` with:
  - `basePath?: string` – starting directory for relative include paths.
  - `includeResolver?: (path: string, ctx: { parentPath: string; depth: number }) => Promise<{ source: string; resolvedPath?: string }>` – resolves a referenced file to source text (optionally returning the canonical path).
  - `maxIncludeDepth?: number` – guard against cycles (default e.g. 16).
- Update `parseAsync` to require the resolver when includes appear; `parse` remains synchronous and skips include expansion.

## Execution flow
1. Parse the parent file to a CST that still contains `include` directives.
2. When `includeResolver` exists, walk the CST/AST for `include` directives:
   - Resolve relative to `basePath` or the including file’s resolved path.
   - Await the resolver; on failure, push a diagnostic and leave the include unresolved.
   - Parse the returned source via `parseAsync` recursively (passing updated `basePath` and incremented depth).
   - Attach the parsed document (or null) to the include node (`IAstInclude` style structure).
3. Track visited paths to prevent infinite recursion; emit a warning when the limit hits.
4. Provide hooks so consumers can decide whether to inline the included CST, merge AST nodes, or simply read the resolved document reference.

## Testing
- Mock resolver returning fixture strings to avoid real FS I/O in unit tests.
- Cover success path, missing file error, depth limit, and circular dependency cases.

## Open questions
- Should synchronous `parse` optionally accept a resolver that returns cached data immediately, or do we keep the split strict?
- Do we expose helper utilities for file-system based resolvers (e.g., Node `fs/promises` implementation) in this package or another module?
