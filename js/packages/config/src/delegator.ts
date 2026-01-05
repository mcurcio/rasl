/**
 * Directive delegator for processing config files.
 *
 * Provides a strongly-typed hook system for directive handlers,
 * supporting scoped processing and include handling.
 */

import type { IAstDirective, IAstDocument } from "./ast.js";

/**
 * Result of a directive handler that opens a new scope.
 */
export interface IScopeResult<TChildContext> {
  /** Delegator for the child scope */
  scope: DirectiveDelegator<TChildContext>;
  /** Context for the child scope */
  ctx: TChildContext;
}

/**
 * Handler for a directive.
 * Returns a scope result if the directive opens a new scope (has a body).
 */
export type DirectiveHandler<TContext, TChildContext = TContext> = (
  directive: IAstDirective,
  ctx: TContext,
) => void | IScopeResult<TChildContext>;

/**
 * Hooks for delegator lifecycle events.
 */
export interface IDelegatorHooks<TContext> {
  /** Called when entering a scope (document or block) */
  onEnterScope?: (owner: IAstDirective | null, ctx: TContext) => void;
  /** Called when exiting a scope */
  onExitScope?: (owner: IAstDirective | null, ctx: TContext) => void;
  /** Called before processing a directive */
  onBeforeDirective?: (directive: IAstDirective, ctx: TContext) => void;
  /** Called after processing a directive */
  onAfterDirective?: (directive: IAstDirective, ctx: TContext) => void;
  /** Called when an unknown directive is encountered */
  onUnknownDirective?: (directive: IAstDirective, ctx: TContext, legalNames: string[]) => void;
}

/**
 * Directive delegator for processing config files.
 *
 * Supports:
 * - Registering handlers for specific directive names
 * - Parent delegation for inherited handlers
 * - Lifecycle hooks for scope enter/exit
 * - Strongly-typed context passing
 */
export class DirectiveDelegator<TContext> {
  private readonly _handlers = new Map<string, DirectiveHandler<TContext, unknown>>();
  private readonly _parent: DirectiveDelegator<TContext> | null;
  private readonly _hooks: IDelegatorHooks<TContext>;

  constructor(options?: { parent?: DirectiveDelegator<TContext>; hooks?: IDelegatorHooks<TContext> }) {
    this._parent = options?.parent ?? null;
    this._hooks = options?.hooks ?? {};
  }

  /**
   * Register a handler for a directive name.
   */
  register<TChildContext = TContext>(name: string, handler: DirectiveHandler<TContext, TChildContext>): this {
    this._handlers.set(name, handler as DirectiveHandler<TContext, unknown>);
    return this;
  }

  /**
   * Get all legal directive names (including inherited).
   */
  legalDirectives(): string[] {
    const names = new Set<string>();
    let current: DirectiveDelegator<TContext> | null = this;
    while (current) {
      for (const name of current._handlers.keys()) {
        names.add(name);
      }
      current = current._parent;
    }
    return [...names].sort();
  }

  /**
   * Check if a directive name is handled.
   */
  handles(name: string): boolean {
    return this._lookup(name) !== null;
  }

  /**
   * Dispatch a directive to its handler.
   */
  dispatch(directive: IAstDirective, ctx: TContext): void {
    this._hooks.onBeforeDirective?.(directive, ctx);

    const handler = this._lookup(directive.name);
    if (!handler) {
      this._hooks.onUnknownDirective?.(directive, ctx, this.legalDirectives());
      this._hooks.onAfterDirective?.(directive, ctx);
      return;
    }

    const result = handler(directive, ctx);

    // If handler returned a scope and directive has a body, process children
    if (result && directive.body) {
      walkScopeBody(directive, result.scope, result.ctx);
    }

    this._hooks.onAfterDirective?.(directive, ctx);
  }

  /**
   * Look up a handler by name (including parent chain).
   */
  private _lookup(name: string): DirectiveHandler<TContext, unknown> | null {
    const local = this._handlers.get(name);
    if (local) return local;
    return this._parent?._lookup(name) ?? null;
  }

  /**
   * Enter a scope (called by walk functions).
   * @internal
   */
  _enterScope(owner: IAstDirective | null, ctx: TContext): void {
    this._hooks.onEnterScope?.(owner, ctx);
  }

  /**
   * Exit a scope (called by walk functions).
   * @internal
   */
  _exitScope(owner: IAstDirective | null, ctx: TContext): void {
    this._hooks.onExitScope?.(owner, ctx);
  }
}

/**
 * Walk a document with a delegator.
 */
export function walkScopeDocument<TContext>(
  doc: IAstDocument,
  scope: DirectiveDelegator<TContext>,
  ctx: TContext,
): void {
  scope._enterScope(null, ctx);
  for (const directive of doc.children) {
    scope.dispatch(directive, ctx);
  }
  scope._exitScope(null, ctx);
}

/**
 * Walk a directive's body with a delegator.
 */
export function walkScopeBody<TContext>(
  owner: IAstDirective,
  scope: DirectiveDelegator<TContext>,
  ctx: TContext,
): void {
  if (!owner.body) return;
  scope._enterScope(owner, ctx);
  for (const child of owner.body) {
    scope.dispatch(child, ctx);
  }
  scope._exitScope(owner, ctx);
}

/**
 * Create a child delegator that inherits from a parent.
 */
export function createChildDelegator<TContext>(
  parent: DirectiveDelegator<TContext>,
  hooks?: IDelegatorHooks<TContext>,
): DirectiveDelegator<TContext> {
  return new DirectiveDelegator({ parent, hooks });
}
