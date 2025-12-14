/**
 * @rasl/config - Generic nginx-style configuration parsing toolkit
 */

export {
  parse,
  parseAsync,
  type IParseResult,
  type IParseError,
  type IParseConfig,
} from './parser.js';
export {
  type ICstNode,
  type ICstDocument,
  type ICstDirective,
  type ICstTrivia,
  type ICstTriviaItem,
  type ISourceSpan,
  CstNodeKind,
  serializeCst,
} from './cst.js';

export {
  type IToken,
  type ITokenSpan,
  type ILexResult,
  type ILexError,
  TokenType,
  Keywords,
  isTrivia,
  isComment,
} from './tokens.js';

export {
  walkDirectives,
  findDirectives,
  type DirectiveVisitor,
} from './loader.js';

export {
  createAstDirectives,
  toAstDirectives,
  type IAstDirective,
  type IAstDirectiveDocument,
  type IAstDirectiveList,
} from './ast-directives.js';

export {
  DirectiveDelegator,
  type IDelegatorHooks,
  type ScopeDirectiveHandler,
  walkScopeBody,
  walkScopeDocument,
  makeSyntheticDirective,
} from './delegator.js';
