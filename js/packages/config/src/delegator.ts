import type { IAstDirective, IAstDirectiveDocument } from './ast-directives.js';
import type { IToken } from './tokens.js';

export type ScopeDirectiveHandler<TContext> = (
  directive: IAstDirective,
  ctx: TContext
) => void | { scope: DirectiveDelegator<unknown>; ctx: unknown };

export interface IDelegatorHooks<TContext> {
  onEnterScope?: (owner: IAstDirective | null, ctx: TContext) => void;
  onExitScope?: (owner: IAstDirective | null, ctx: TContext) => void;
  onBeforeDirective?: (directive: IAstDirective, ctx: TContext) => void;
  onAfterDirective?: (directive: IAstDirective, ctx: TContext) => void;
  onUnknownDirective?: (directive: IAstDirective, ctx: TContext, legal: string[]) => void;
}

export class DirectiveDelegator<TContext> {
  private readonly _handlers = new Map<string, ScopeDirectiveHandler<TContext>>();
  private readonly _parent: DirectiveDelegator<TContext> | null;
  private readonly _hooks: IDelegatorHooks<TContext> | null;

  constructor(options?: { parent?: DirectiveDelegator<TContext>; hooks?: IDelegatorHooks<TContext> }) {
    this._parent = options?.parent ?? null;
    this._hooks = options?.hooks ?? null;
  }

  register(name: string, handler: ScopeDirectiveHandler<TContext>): this {
    this._handlers.set(name, handler);
    return this;
  }

  legalDirectives(): string[] {
    const names = new Set<string>();
    let cur: DirectiveDelegator<TContext> | null = this;
    while (cur) {
      for (const k of cur._handlers.keys()) names.add(k);
      cur = cur._parent;
    }
    return [...names.values()].sort();
  }

  dispatch(directive: IAstDirective, ctx: TContext): void {
    this._hooks?.onBeforeDirective?.(directive, ctx);

    const handler = this._lookup(directive.name);
    if (!handler) {
      const legal = this.legalDirectives();
      this._hooks?.onUnknownDirective?.(directive, ctx, legal);
      this._hooks?.onAfterDirective?.(directive, ctx);
      return;
    }

    const result = handler(directive, ctx);
    if (result && directive.body) {
      const scope = result.scope as DirectiveDelegator<unknown>;
      const childCtx = result.ctx;
      walkScopeBody(directive, scope, childCtx);
    }

    this._hooks?.onAfterDirective?.(directive, ctx);
  }

  private _lookup(name: string): ScopeDirectiveHandler<TContext> | null {
    const local = this._handlers.get(name);
    if (local) return local;
    return this._parent?._lookup(name) ?? null;
  }

  _enterScope(owner: IAstDirective | null, ctx: TContext): void {
    this._hooks?.onEnterScope?.(owner, ctx);
  }

  _exitScope(owner: IAstDirective | null, ctx: TContext): void {
    this._hooks?.onExitScope?.(owner, ctx);
  }
}

export function walkScopeDocument<TContext>(
  doc: IAstDirectiveDocument,
  scope: DirectiveDelegator<TContext>,
  ctx: TContext
): void {
  scope._enterScope(null, ctx);
  for (const dir of doc.children) scope.dispatch(dir, ctx);
  scope._exitScope(null, ctx);
}

export function walkScopeBody<TContext>(
  owner: IAstDirective,
  scope: DirectiveDelegator<TContext>,
  ctx: TContext
): void {
  if (!owner.body) return;
  scope._enterScope(owner, ctx);
  for (const child of owner.body) scope.dispatch(child, ctx);
  scope._exitScope(owner, ctx);
}

class SyntheticDirectiveView implements IAstDirective {
  readonly cst: IAstDirective['cst'];

  private readonly _source: IAstDirective;
  private readonly _nameToken: IToken;
  private readonly _argsStartIndex: number;

  constructor(source: IAstDirective, nameToken: IToken, argsStartIndex: number) {
    this._source = source;
    this._nameToken = nameToken;
    this._argsStartIndex = argsStartIndex;
    this.cst = source.cst;
  }

  get name(): string {
    return this._nameToken.value;
  }

  set name(value: string) {
    this._nameToken.value = value;
  }

  get args(): IToken[] {
    return this._source.args.slice(this._argsStartIndex);
  }

  set args(value: IToken[]) {
    const prefix = this._source.args.slice(0, this._argsStartIndex);
    this._source.args = [...prefix, ...value];
  }

  get body(): IAstDirective['body'] {
    return this._source.body;
  }

  set body(value: IAstDirective['body']) {
    this._source.body = value;
  }

  get span(): IAstDirective['span'] {
    return this._source.span;
  }
}

export function makeSyntheticDirective(source: IAstDirective, nameToken: IToken, args: IToken[]): IAstDirective {
  // We intentionally ignore the provided args array for storage and instead treat
  // it as a view into the source args. This keeps the synthetic directive as a
  // virtual facade over the underlying CST-backed source directive.
  void args;

  const idx = source.args.indexOf(nameToken);
  const start = (idx >= 0 ? idx : 0) + 1;
  return new SyntheticDirectiveView(source, nameToken, start);
}
