/**
 * AST facade over the CST for convenient directive traversal and editing.
 *
 * The AST provides a simpler view for consumers who don't need byte-identical
 * round-tripping. Edits through the AST modify the underlying CST.
 */

import { getDirectiveArgs, getDirectiveName, getSpanForRange, type ICstDirective, type ICstDocument } from "./cst.js";
import type { ISourceSpan, IToken } from "./tokens.js";

/**
 * AST document wrapping a CST document.
 */
export interface IAstDocument {
  /** Top-level directives */
  readonly children: IAstDirectiveList;
  /** Underlying CST document */
  readonly cst: ICstDocument;
}

/**
 * List of AST directives with array-like operations.
 */
export interface IAstDirectiveList extends Iterable<IAstDirective> {
  readonly length: number;
  at(index: number): IAstDirective | undefined;
  toArray(): IAstDirective[];
  find(predicate: (d: IAstDirective) => boolean): IAstDirective | undefined;
  filter(predicate: (d: IAstDirective) => boolean): IAstDirective[];
  findByName(name: string): IAstDirective | undefined;
  filterByName(name: string): IAstDirective[];
}

/**
 * AST directive providing convenient access to directive properties.
 */
export interface IAstDirective {
  /** Owning AST document (for provenance and access to the CST) */
  readonly document: IAstDocument;
  /** Directive name */
  readonly name: string;
  /** Argument tokens */
  readonly args: IToken[];
  /** Argument values (convenience accessor) */
  readonly argValues: (string | number | boolean)[];
  /** Child directives if this is a block */
  readonly body: IAstDirectiveList | null;
  /** Source span */
  readonly span: ISourceSpan;
  /** Underlying CST directive */
  readonly cst: ICstDirective;
}

/**
 * Internal factory for creating AST nodes with caching.
 */
class AstFactory {
  private readonly _astDoc: IAstDocument;
  private readonly _doc: ICstDocument;
  private readonly _directiveCache = new WeakMap<ICstDirective, AstDirective>();

  constructor(astDoc: IAstDocument, doc: ICstDocument) {
    this._astDoc = astDoc;
    this._doc = doc;
  }

  directive(cst: ICstDirective): AstDirective {
    let cached = this._directiveCache.get(cst);
    if (!cached) {
      cached = new AstDirective(this, this._astDoc, this._doc, cst);
      this._directiveCache.set(cst, cached);
    }
    return cached;
  }

  list(cstList: ICstDirective[]): AstDirectiveList {
    return new AstDirectiveList(this, cstList);
  }
}

/**
 * Implementation of IAstDirective.
 */
class AstDirective implements IAstDirective {
  private readonly _factory: AstFactory;
  readonly document: IAstDocument;
  private readonly _doc: ICstDocument;
  readonly cst: ICstDirective;

  constructor(factory: AstFactory, astDoc: IAstDocument, doc: ICstDocument, cst: ICstDirective) {
    this._factory = factory;
    this.document = astDoc;
    this._doc = doc;
    this.cst = cst;
  }

  get name(): string {
    return getDirectiveName(this._doc, this.cst);
  }

  get args(): IToken[] {
    return getDirectiveArgs(this._doc, this.cst);
  }

  get argValues(): (string | number | boolean)[] {
    return this.args.map((t) => t.value);
  }

  get body(): IAstDirectiveList | null {
    if (!this.cst.body) return null;
    return this._factory.list(this.cst.body);
  }

  get span(): ISourceSpan {
    return getSpanForRange(this._doc, this.cst.tokenRange);
  }
}

/**
 * Implementation of IAstDirectiveList.
 */
class AstDirectiveList implements IAstDirectiveList {
  private readonly _factory: AstFactory;
  private readonly _cstList: ICstDirective[];

  constructor(factory: AstFactory, cstList: ICstDirective[]) {
    this._factory = factory;
    this._cstList = cstList;
  }

  get length(): number {
    return this._cstList.length;
  }

  at(index: number): IAstDirective | undefined {
    const cst = this._cstList.at(index);
    return cst ? this._factory.directive(cst) : undefined;
  }

  toArray(): IAstDirective[] {
    return this._cstList.map((cst) => this._factory.directive(cst));
  }

  find(predicate: (d: IAstDirective) => boolean): IAstDirective | undefined {
    for (const cst of this._cstList) {
      const ast = this._factory.directive(cst);
      if (predicate(ast)) return ast;
    }
    return undefined;
  }

  filter(predicate: (d: IAstDirective) => boolean): IAstDirective[] {
    const result: IAstDirective[] = [];
    for (const cst of this._cstList) {
      const ast = this._factory.directive(cst);
      if (predicate(ast)) result.push(ast);
    }
    return result;
  }

  findByName(name: string): IAstDirective | undefined {
    return this.find((d) => d.name === name);
  }

  filterByName(name: string): IAstDirective[] {
    return this.filter((d) => d.name === name);
  }

  [Symbol.iterator](): Iterator<IAstDirective> {
    let index = 0;
    return {
      next: (): IteratorResult<IAstDirective> => {
        if (index >= this._cstList.length) {
          return { done: true, value: undefined };
        }
        const cst = this._cstList[index++];
        return { done: false, value: this._factory.directive(cst) };
      },
    };
  }
}

/**
 * Implementation of IAstDocument.
 */
class AstDocument implements IAstDocument {
  readonly cst: ICstDocument;
  readonly children: IAstDirectiveList;

  constructor(cst: ICstDocument) {
    this.cst = cst;
    const factory = new AstFactory(this, cst);
    this.children = factory.list(cst.children);
  }
}

/**
 * Create an AST facade over a CST document.
 */
export function createAst(cst: ICstDocument): IAstDocument {
  return new AstDocument(cst);
}

/**
 * Walk all directives in a document depth-first.
 */
export function walkDirectives(
  doc: IAstDocument,
  visitor: (directive: IAstDirective, parent: IAstDirective | null) => void,
): void {
  const visit = (directive: IAstDirective, parent: IAstDirective | null): void => {
    visitor(directive, parent);
    if (directive.body) {
      for (const child of directive.body) {
        visit(child, directive);
      }
    }
  };

  for (const child of doc.children) {
    visit(child, null);
  }
}

/**
 * Find all directives with the given name anywhere in the document.
 */
export function findDirectives(doc: IAstDocument, name: string): IAstDirective[] {
  const result: IAstDirective[] = [];
  walkDirectives(doc, (directive) => {
    if (directive.name === name) {
      result.push(directive);
    }
  });
  return result;
}
