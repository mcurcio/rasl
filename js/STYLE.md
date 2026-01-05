# RASL TypeScript Style Guide

This document describes how we write TypeScript in `js/`. It focuses on readability, safety, and idiomatic TS (not “Python in TS”).

## 1. Language settings

1.1 Assume `strict: true` TypeScript. Make invalid states unrepresentable where practical.  
1.2 Prefer compile-time guarantees over runtime cleverness. Add runtime validation only at boundaries (untrusted inputs, IO).  
1.3 Prefer ESM-friendly patterns; avoid CommonJS assumptions.

## 2. Built-in types (avoid boxed primitives)

2.1 Use `string`, `number`, `bigint`, `boolean`, `symbol` and not the boxed object types `String`, `Number`, `Boolean` (TypeScript explicitly discourages boxed types).  
2.2 Use `unknown` for untrusted values, not `any`.

## 3. Naming

3.1 `camelCase` for variables, functions, parameters, and non-class methods.  
3.2 `PascalCase` for classes, `interface`s, types, and `enum`s.  
3.3 `SCREAMING_SNAKE_CASE` for exported constants that are truly constant.  
3.4 Private fields: choose one convention repo-wide; until then, follow existing patterns in the package (`_field` is currently common).  
3.5 File names: prefer `kebab-case.ts` for multiword files.

## 4. Modules, exports, and imports

4.1 Prefer named exports over default exports.  
4.2 Public APIs should export types explicitly and intentionally; do not “export *” from deep internals unless the file is an explicit barrel.  
4.3 Avoid deep imports into other packages’ `src/` or `dist/`. Import from package roots.  
4.4 Type-only imports use `import type { X } from '…'` (recommended by typescript-eslint’s `consistent-type-imports`).  
4.5 In `NodeNext`/ESM packages, prefer explicit `.js` specifiers for local relative imports when the repo already follows that pattern (so emitted JS matches runtime resolution).

## 5. Types: `interface` vs `type`

5.1 Use `interface` for public API contracts and objects meant to be implemented/extended.  
5.2 Use `type` for unions, intersections, mapped types, conditional types, and “data shapes” that are not meant to be implemented.  
5.3 Prefer composition over inheritance: keep interfaces small and focused.  
5.4 Avoid “dictionary” types like `{ [k: string]: any }`. Use `Record<string, T>` or `Map<K, V>` with a real value type.

## 6. Enums and “enum-like” values

There is no single “best” here. Choose based on whether you need a runtime value.

6.1 If you only need a closed set in the type system, use a string-literal union:

- `export type ColorModel = 'srgb' | 'oklab' | 'oklch';`

6.2 If you need runtime values (iteration, mapping, validation) and a type, use an `as const` object:

- `export const ColorModels = { Srgb: 'srgb', Oklab: 'oklab' } as const;`
- `export type ColorModel = (typeof ColorModels)[keyof typeof ColorModels];`

6.3 If an `enum` is genuinely the cleanest option, prefer **string enums**.  
6.4 Avoid numeric enums unless you have a strong reason (numeric values are opaque at runtime; reverse mappings can surprise). Avoid heterogeneous enums (TypeScript docs explicitly advise against them).  
6.5 Avoid `const enum` unless we explicitly standardize tooling around it (it can interact poorly with some build pipelines).

## 7. Function and API design

7.1 Prefer small pure functions; isolate IO at the edges.  
7.2 Exported/public functions should have explicit parameter types; add explicit return types when the function is part of a public API surface or when inference would hide a breaking change.  
7.3 Prefer options objects for functions with more than ~2–3 optional parameters. Name option types `XOptions`.  
7.4 Prefer `readonly` inputs (`readonly T[]`, `ReadonlyMap`, `ReadonlySet`) and avoid mutating caller-owned data.  
7.5 Avoid throwing for expected control flow. Use `Result`-like return types when callers are expected to handle failures frequently.

## 8. `null`/`undefined`, truthiness, and defaults

8.1 Prefer `undefined` for “missing”; use `null` only when it carries meaning.  
8.2 Use `??` for defaults, not `||` (unless empty string/0 should also trigger the default).  
8.3 Use optional chaining (`?.`) for safe access; avoid broad truthiness checks on values that can validly be `0`/`''`/`false`.

## 9. `any`, `unknown`, and validation

9.1 Do not introduce new `any` in core logic. If unavoidable, quarantine it at a boundary and add a test covering the expected shape.  
9.2 Use `unknown` for untrusted data and narrow via:

- type guards (`function isX(v: unknown): v is X`)
- schema validation (only at boundaries)

9.3 Prefer `satisfies` when declaring objects that must match a type but should retain precise inference.  
9.4 Avoid `as X` type assertions as a general escape hatch. Prefer narrowing/validation. Use `as const` intentionally to preserve literals.

## 10. Errors and diagnostics

10.1 Throw `Error` subclasses for exceptional cases where stack traces matter.  
10.2 For user-facing diagnostics, include structured context:

- `code` (string)
- `message` (human-friendly)
- `span` / `location` (line/column when applicable)
- `cause` (when wrapping)

10.3 Prefer caret-style snippets for parse/config errors (`^^^^`) and ensure errors can be rendered as colorized console output without losing structure.

## 11. Async and cancellation

11.1 Prefer async APIs when IO is involved; avoid “sometimes sync, sometimes async” surfaces.  
11.2 Prefer `AbortSignal` for cancellation where long-running operations exist.  
11.3 Avoid floating promises. Handle them via `await`, `return`, `.catch()`, or intentionally `void` them (typescript-eslint’s `no-floating-promises` describes the acceptable handling patterns).  
11.4 Prefer `Promise.all([...])`/`Promise.allSettled([...])` when you intentionally run tasks concurrently.

## 12. Testing (Vitest)

12.1 Tests should read like documentation: arrange/act/assert; small focused assertions.  
12.2 Prefer deterministic tests (control time and randomness where possible).  
12.3 For numeric behavior, compare with epsilon tolerance and document the chosen tolerance in the test.

## 13. References

13.1 TypeScript handbook: https://www.typescriptlang.org/docs/handbook/  
13.2 TypeScript enums reference: https://www.typescriptlang.org/docs/handbook/enums.html  
13.3 typescript-eslint rules (esp. `no-explicit-any`, `consistent-type-imports`, `no-floating-promises`): https://typescript-eslint.io/rules/

## 14. Repo-level decisions to confirm

14.1 Keep the `IThing` naming convention for interfaces/types, or switch to `Thing`?  
14.2 Standardize on `_privateField` or `#privateField`?  
14.3 Enforce Prettier (and with what options), and enforce import sorting?  
14.4 Define a standard `Result<T, E>` pattern for expected failures?  
14.5 Standardize a base `RaslError`/diagnostic shape across packages?
