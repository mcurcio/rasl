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
3.2 `PascalCase` for classes, `interface`s, types, and “enum-like” constant objects.  
3.3 `SCREAMING_SNAKE_CASE` for exported constants that are truly constant.  
3.4 Private fields use `#privateField` by default. Use `private _field` only when a specific use case makes `#private` impractical (e.g., you explicitly need subclass access, or you need to inspect/mutate internals in tests).  
3.5 File names: prefer `kebab-case.ts` for multiword files.
3.6 `interface`s use the `I` prefix (e.g., `INode`, `ISchedulerConfig`). Non-interface `type`s do not.

## 4. Modules, exports, and imports

4.1 Use named exports. Avoid default exports.  
4.2 Public APIs should export types explicitly and intentionally; do not “export *” from deep internals unless the file is an explicit barrel.  
4.3 Avoid deep imports into other packages’ `src/` or `dist/`. Import from package roots.  
4.4 Type-only imports use `import type { X } from '…'` (recommended by typescript-eslint’s `consistent-type-imports`).  
4.5 In `NodeNext`/ESM packages, prefer explicit `.js` specifiers for local relative imports when the repo already follows that pattern (so emitted JS matches runtime resolution).
4.6 Keep imports sorted; prefer an automated tool (ESLint rule or TS-based organizer) over manual ordering.

## 5. Types: `interface` vs `type`

5.1 Use `interface` for public API contracts and objects meant to be implemented/extended.  
5.2 Use `type` for unions, intersections, mapped types, conditional types, and “data shapes” that are not meant to be implemented.  
5.3 Prefer composition over inheritance: keep interfaces small and focused.  
5.4 Avoid “dictionary” types like `{ [k: string]: any }`. Use `Record<string, T>` or `Map<K, V>` with a real value type.

## 6. Enums and “enum-like” values

6.1 We use one style for “enum-like” sets: an `as const` object with a derived union type.

6.2 Define values like this:

- `export const ColorModels = { Srgb: 'srgb', Oklab: 'oklab' } as const;`
- `export type ColorModel = (typeof ColorModels)[keyof typeof ColorModels];`

6.3 Do not use `enum` or `const enum`.

## 7. Function and API design

7.1 Prefer small pure functions; isolate IO at the edges.  
7.2 All functions should have an explicit return type (documented in the signature). Prefer inference for local *callbacks* only.  
7.3 Prefer options objects for functions with more than ~2–3 optional parameters. Name option types `XOptions`.  
7.4 Prefer `readonly` inputs (`readonly T[]`, `ReadonlyMap`, `ReadonlySet`) and avoid mutating caller-owned data.  
7.5 Throwing/rejecting is reasonable for domain operations when failure is an error (e.g., `NotFound`, `DatabaseTimedOut`). Prefer typed `Error` subclasses (or a standard error shape) so callers can distinguish cases reliably.

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
10.4 Prefer domain-specific error hierarchies per module:

- `MyModuleError extends Error`
- `MyModuleNotFoundError extends MyModuleError`
- `MyModuleTimedOutError extends MyModuleError`

10.5 Prefer a shared, enum-like `ErrorCode` set (as `as const`, not `enum`) for cross-cutting categories.
10.6 User-input / parse failures should throw (they are failures of the operation’s contract).

## 11. Async and cancellation

11.1 Prefer async APIs when IO is involved; avoid “sometimes sync, sometimes async” surfaces.  
11.2 Prefer `AbortSignal` for cancellation where long-running operations exist.  
11.3 Avoid floating promises. Handle them via `await`, `return`, `.catch()`, or intentionally `void` them (typescript-eslint’s `no-floating-promises` describes the acceptable handling patterns).  
11.4 Prefer `Promise.all([...])`/`Promise.allSettled([...])` when you intentionally run tasks concurrently.

## 12. Generics

12.1 Prefer generics to reduce duplication when the abstraction is real and improves reuse.  
12.2 Prefer generic functions over generic classes unless instances must carry the type parameter.  
12.3 Use constraints to keep generics honest (`<T extends X>`), and default type parameters when there is an obvious default.  
12.4 Avoid “over-generic” APIs that erase meaning (e.g., `<T>(x: T) => T` when the domain really wants a concrete type).  
12.5 Prefer `readonly` generic collections for inputs (`readonly T[]`) and return new values instead of mutating inputs.  

## 13. Testing (Vitest)

13.1 Tests should read like documentation: arrange/act/assert; small focused assertions.  
13.2 Prefer deterministic tests (control time and randomness where possible).  
13.3 For numeric behavior, compare with epsilon tolerance and document the chosen tolerance in the test.

## 14. References

14.1 TypeScript handbook: https://www.typescriptlang.org/docs/handbook/  
14.2 TypeScript enums reference (background; we avoid enums in RASL): https://www.typescriptlang.org/docs/handbook/enums.html  
14.3 typescript-eslint rules (esp. `no-explicit-any`, `consistent-type-imports`, `no-floating-promises`): https://typescript-eslint.io/rules/

## 15. Repo-level decisions to confirm

15.1 Enforce Prettier (and with what options), and enforce import sorting (which tool/rules)?  
15.2 Define the shared `ErrorCode` list (names + intended semantics).  
15.3 Standardize a minimal base diagnostic shape (`code`, `message`, `cause`, optional `span`) for errors that carry user-facing context.
