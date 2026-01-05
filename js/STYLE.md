# RASL TypeScript Style Guide

This document describes how we write TypeScript in `js/`. It focuses on readability, safety, and idiomatic TS (not “Python in TS”).

## 1. Language settings

1.1 Assume `strict: true` TypeScript. Make invalid states unrepresentable where practical.  
1.2 Prefer compile-time guarantees over runtime cleverness. Add runtime validation only at boundaries (untrusted inputs, IO).  
1.3 Prefer ESM-friendly patterns; avoid CommonJS assumptions.

## 2. Naming

2.1 `camelCase` for variables, functions, parameters, and non-class methods.  
2.2 `PascalCase` for classes, `interface`s, types, enums, and namespaces/modules.  
2.3 `SCREAMING_SNAKE_CASE` for exported constants that are truly constant (not configuration objects that consumers mutate).  
2.4 Private fields follow the repo’s current pattern: `private _thing` / `private readonly _thing` (avoid `#private` unless we standardize on it).  
2.5 File names: prefer `kebab-case.ts` for multiword files.

## 3. Modules, exports, and imports

3.1 Prefer named exports over default exports.  
3.2 Public APIs should export types explicitly and intentionally; do not “export *” from deep internals unless the file is an explicit barrel.  
3.3 Avoid deep imports into other packages’ `src/` or `dist/`. Import from package roots.  
3.4 Type-only imports use `import type { X } from '…'`.  
3.5 In `NodeNext`/ESM packages, prefer explicit `.js` specifiers for local relative imports when the repo already follows that pattern (so emitted JS matches runtime resolution).

## 4. Types: `interface` vs `type`

4.1 Use `interface` for public API contracts and objects meant to be implemented/extended.  
4.2 Use `type` for unions, intersections, mapped types, conditional types, and “data shapes” that are not meant to be implemented.  
4.3 Prefer composition over inheritance: keep interfaces small and focused.  
4.4 Avoid “dictionary” types like `{ [k: string]: any }`. Use `Record<string, T>` or `Map<K, V>` with a real value type.

## 5. Enums and “enum-like” values

5.1 Prefer string-literal unions over `enum`:

- `export type ColorModel = 'srgb' | 'oklab' | 'oklch';`

5.2 When you want a runtime value *and* a type, prefer `as const` objects:

- `export const ColorModels = { Srgb: 'srgb', Oklab: 'oklab' } as const;`
- `export type ColorModel = (typeof ColorModels)[keyof typeof ColorModels];`

5.3 Avoid numeric enums. Avoid `const enum` unless explicitly agreed.

## 6. Function and API design

6.1 Prefer small pure functions; isolate IO at the edges.  
6.2 Exported functions/methods should have explicit parameter and return types (even when inference would work).  
6.3 Prefer options objects for functions with more than ~2–3 optional parameters. Name option types `XOptions`.  
6.4 Prefer `readonly` inputs (`readonly T[]`, `ReadonlyMap`, `ReadonlySet`) and avoid mutating caller-owned data.  
6.5 Avoid throwing for expected control flow. Use `Result`-like return types when callers are expected to handle failures frequently.

## 7. `null`/`undefined`, truthiness, and defaults

7.1 Prefer `undefined` for “missing”; use `null` only when it carries meaning.  
7.2 Use `??` for defaults, not `||` (unless empty string/0 should also trigger the default).  
7.3 Use optional chaining (`?.`) for safe access; avoid broad truthiness checks on values that can validly be `0`/`''`/`false`.

## 8. `any`, `unknown`, and validation

8.1 Do not introduce new `any` in core logic. If unavoidable, quarantine it at a boundary and add a test covering the expected shape.  
8.2 Use `unknown` for untrusted data and narrow via:

- type guards (`function isX(v: unknown): v is X`)
- schema validation (only at boundaries)

8.3 Prefer `satisfies` when declaring objects that must match a type but should retain precise inference.

## 9. Errors and diagnostics

9.1 Throw `Error` subclasses for exceptional cases where stack traces matter.  
9.2 For user-facing diagnostics, include structured context:

- `code` (string)
- `message` (human-friendly)
- `span` / `location` (line/column when applicable)
- `cause` (when wrapping)

9.3 Prefer caret-style snippets for parse/config errors (`^^^^`) and ensure errors can be rendered as colorized console output without losing structure.

## 10. Async and cancellation

10.1 Prefer async APIs when IO is involved; avoid “sometimes sync, sometimes async” surfaces.  
10.2 Prefer `AbortSignal` for cancellation where long-running operations exist.  
10.3 Avoid floating promises; `await` or intentionally `void` them with an explanation in rare cases.

## 11. Testing (Vitest)

11.1 Tests should read like documentation: arrange/act/assert; small focused assertions.  
11.2 Prefer deterministic tests (control time and randomness where possible).  
11.3 For numeric behavior, compare with epsilon tolerance and document the chosen tolerance in the test.

## 12. Decision points to confirm

12.1 Keep the `IThing` naming convention for interfaces/types, or switch to `Thing`?  
12.2 Standardize on `_privateField` or `#privateField`?  
12.3 Enforce Prettier (and with what options), and enforce import sorting?  
12.4 Define a standard `Result<T, E>` pattern for expected failures?  
12.5 Standardize a base `RaslError`/diagnostic shape across packages?

