import type { ICstDirective, ICstDocument, ISourceSpan } from './cst.js';
import type { IToken } from './tokens.js';

export interface IAstDirectiveDocument {
  children: IAstDirectiveList;
  cst: ICstDocument;
}

export interface IAstDirectiveList extends Iterable<IAstDirective> {
  readonly length: number;
  at(index: number): IAstDirective | undefined;
  toArray(): IAstDirective[];
  push(...items: IAstDirective[]): number;
  splice(start: number, deleteCount?: number, ...items: IAstDirective[]): IAstDirective[];
}

export interface IAstDirective {
  name: string;
  args: IToken[];
  body: IAstDirectiveList | null;
  span: ISourceSpan;
  cst: ICstDirective;
}

class AstDirective implements IAstDirective {
  readonly cst: ICstDirective;

  private readonly _factory: AstFactory;

  constructor(factory: AstFactory, cst: ICstDirective) {
    this._factory = factory;
    this.cst = cst;
  }

  get name(): string {
    return this.cst.name;
  }

  set name(value: string) {
    this.cst.name = value;
  }

  get args(): IToken[] {
    return this.cst.args;
  }

  set args(value: IToken[]) {
    this.cst.args = value;
  }

  get body(): IAstDirectiveList | null {
    if (!this.cst.body) return null;
    return new AstDirectiveList(this._factory, () => this.cst.body ?? [], (next) => {
      this.cst.body = next;
    });
  }

  set body(value: IAstDirectiveList | null) {
    if (!value) {
      this.cst.body = null;
      return;
    }
    this.cst.body = value.toArray().map((d) => d.cst);
  }

  get span(): ISourceSpan {
    return this.cst.span;
  }
}

class AstDirectiveList implements IAstDirectiveList {
  private readonly _factory: AstFactory;
  private readonly _get: () => ICstDirective[];
  private readonly _set: (next: ICstDirective[]) => void;

  constructor(factory: AstFactory, get: () => ICstDirective[], set: (next: ICstDirective[]) => void) {
    this._factory = factory;
    this._get = get;
    this._set = set;
  }

  get length(): number {
    return this._get().length;
  }

  at(index: number): IAstDirective | undefined {
    const dir = this._get().at(index);
    return dir ? this._factory.directive(dir) : undefined;
  }

  toArray(): IAstDirective[] {
    return this._get().map((d) => this._factory.directive(d));
  }

  push(...items: IAstDirective[]): number {
    const arr = this._get();
    arr.push(...items.map((d) => d.cst));
    this._set(arr);
    return arr.length;
  }

  splice(start: number, deleteCount?: number, ...items: IAstDirective[]): IAstDirective[] {
    const arr = this._get();
    const removed =
      deleteCount === undefined
        ? arr.splice(start)
        : arr.splice(start, deleteCount, ...items.map((d) => d.cst));
    this._set(arr);
    return removed.map((d) => this._factory.directive(d));
  }

  [Symbol.iterator](): Iterator<IAstDirective> {
    let i = 0;
    const items = this._get();
    return {
      next: (): IteratorResult<IAstDirective> => {
        const value = items[i];
        if (!value) return { done: true, value: undefined };
        i++;
        return { done: false, value: this._factory.directive(value) };
      },
    };
  }
}

class AstDirectiveDocument implements IAstDirectiveDocument {
  readonly cst: ICstDocument;
  readonly children: IAstDirectiveList;

  private readonly _factory: AstFactory;

  constructor(cst: ICstDocument) {
    this._factory = new AstFactory();
    this.cst = cst;
    this.children = new AstDirectiveList(this._factory, () => this.cst.children, (next) => {
      this.cst.children = next;
    });
  }
}

class AstFactory {
  private readonly _cache = new WeakMap<ICstDirective, AstDirective>();

  directive(cst: ICstDirective): AstDirective {
    const existing = this._cache.get(cst);
    if (existing) return existing;
    const created = new AstDirective(this, cst);
    this._cache.set(cst, created);
    return created;
  }
}

export function createAstDirectives(doc: ICstDocument): IAstDirectiveDocument {
  return new AstDirectiveDocument(doc);
}

export function toAstDirectives(doc: ICstDocument): IAstDirectiveDocument {
  return createAstDirectives(doc);
}
