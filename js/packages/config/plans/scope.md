# Directive delegator scope plan

## Goals

- Make `DirectiveDelegator` easier to compose when building DSL layers on top of the directive AST.
- Default to walking child directives with the current scope/context while still allowing handlers to redirect child processing.
- Improve observability (hooks) without forcing each handler to hand-roll `{ scope, ctx }` objects.
- Make it a solid foundation for post-parse passes like `include` resolution.
- Keep the public API strongly typed (avoid `unknown`/`any` where possible).

## Proposed API refinements

1. **Default child traversal**
   - After a handler runs, automatically walk `directive.body` using the same delegator/context unless the handler opts out (`return Delegate.skipChildren()`).
   - This aligns with intuition: most directives want their nested directives handled by the same scope.
2. **Explicit child delegation helpers**
   - Provide helpers such as `return Delegate.childrenWith(scope, ctx)` or `return Delegate.childrenHere(ctxOverride?)`.
   - Helpers return small tagged objects understood by the delegator, avoiding ad-hoc `{ scope, ctx }` shapes.
3. **Scoped overrides**
   - Allow handlers to temporarily push a child scope without creating a brand-new delegator instance each time (e.g., `scope.withChild(childScope, childCtx, () => { ... })`).
4. **Hooks**
   - Keep `onEnterScope`, `onExitScope`, `onBeforeDirective`, `onAfterDirective`, `onUnknownDirective`.
   - Add `onSkipDirective` to detect when children are intentionally skipped.
5. **Strong typing for delegation results**
   - Replace `void | { scope: DirectiveDelegator<unknown>; ctx: unknown }` with a discriminated union that preserves types:
     - `Delegate.children(ctxOverride?)`
     - `Delegate.childrenWith(scope, childCtx)`
     - `Delegate.skipChildren()`
   - Ensure `childrenWith` carries a `DirectiveDelegator<TChildCtx>` and `TChildCtx` without casts.
6. **Minimal registration API (optional wrapper)**
   - Provide a thin “register directives + callbacks” API on top of `DirectiveDelegator` so minimal consumers don’t need to reason about scopes directly.

## Change strategy

- Treat any change to default traversal or handler return shapes as a breaking change.
- If compatibility shims are desired, decide that explicitly (default: no shims/aliases/deprecations).

## Open questions

- Do we need per-directive context merges (e.g., deriving child context from parent return value)?
- Should the delegator expose a way to mutate directive arguments in-place, or should that stay outside scope?
