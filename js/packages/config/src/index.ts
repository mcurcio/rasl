/**
 * @rasl/config - Configuration file parsing for RASL
 */

export {
  parse,
  parseAsync,
  type IParseResult,
  type IParseError,
  type IParseConfig,
  type IncludeResolver,
} from './parser.js';
export {
  type ICstNode,
  type ICstDocument,
  type ICstNodeBlock,
  type ICstConnection,
  type ICstProperty,
  type ICstInclude,
  type ICstFill,
  type ICstLineComment,
  type ICstBlockComment,
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
  isKeyword,
  isTrivia,
  isComment,
} from './tokens.js';
export {
  type IAstDocument,
  type IAstNodeDef,
  type IAstConnection,
  type IAstProperty,
  type IAstInclude,
  type ISliceSpec,
} from './ast.js';
