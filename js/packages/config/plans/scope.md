# Directive delegator scope plan

## Goals
- Make `DirectiveDelegator` easier to compose when building DSL layers on top of the directive AST.
- Default to walking child directives with the current scope/context while still allowing handlers to redirect child processing.
- Improve observability (hooks) without forcing each handler to hand-roll `{ scope, ctx }` objects.

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

## Migration plan
- Introduce the new helper return types while still accepting the legacy `{ scope, ctx }` object for one release (with console warnings) to ease adoption.
- Update internal usage/tests to exercise default traversal, skipping, and re-scoping flows.

## Open questions
- Do we need per-directive context merges (e.g., deriving child context from parent return value)?
- Should the delegator expose a way to mutate directive arguments in-place, or should that stay outside scope?
