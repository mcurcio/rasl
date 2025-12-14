/**
 * Concrete Syntax Tree types for RASL config files.
 *
 * The CST preserves all source information including whitespace and comments,
 * enabling lossless round-tripping and precise error reporting.
 */

/**
 * CST node kinds.
 */
export const CstNodeKind = {
  Document: 'document',
  NodeBlock: 'node_block',
  Connection: 'connection',
  Property: 'property',
  Identifier: 'identifier',
  Literal: 'literal',
  LineComment: 'line_comment',
  BlockComment: 'block_comment',
  Include: 'include',
  Fill: 'fill',
  Trivia: 'trivia',
} as const;
export type CstNodeKind = (typeof CstNodeKind)[keyof typeof CstNodeKind];

/**
 * Source location span.
 */
export interface ISourceSpan {
  start: number;
  end: number;
  line: number;
  column: number;
}

/**
 * Trivia attached to a CST node (for round-tripping).
 */
export interface ICstTrivia {
  leadingTrivia: ICstTriviaItem[];
  trailingTrivia: ICstTriviaItem[];
}

/**
 * A single trivia item (whitespace or comment).
 */
export interface ICstTriviaItem {
  kind: 'whitespace' | 'newline' | 'line_comment' | 'block_comment';
  text: string;
  span: ISourceSpan;
}

/**
 * Base interface for all CST nodes.
 * Includes trivia for lossless round-tripping.
 */
export interface ICstNode {
  kind: CstNodeKind;
  span: ISourceSpan;
  trivia?: ICstTrivia;
}

/**
 * Root document node.
 */
export interface ICstDocument extends ICstNode {
  kind: typeof CstNodeKind.Document;
  children: ICstNode[];
}

/**
 * Node definition block.
 * Example: `node Waveform sine { ... }`
 */
export interface ICstNodeBlock extends ICstNode {
  kind: typeof CstNodeKind.NodeBlock;
  nodeType: string;
  nodeId: string;
  properties: ICstProperty[];
  connections: ICstConnection[];
}

/**
 * Connection statement.
 * Example: `connect source_node;` or `connect source_node target_port;`
 */
export interface ICstConnection extends ICstNode {
  kind: typeof CstNodeKind.Connection;
  sourceNode: string;
  sourcePort?: string;
  targetPort?: string;
  slice?: string;
}

/**
 * Property assignment.
 * Example: `frequency_hz 0.5;`
 */
export interface ICstProperty extends ICstNode {
  kind: typeof CstNodeKind.Property;
  name: string;
  value: string | number | boolean;
}

/**
 * Include directive.
 * Example: `include "./common.conf";`
 */
export interface ICstInclude extends ICstNode {
  kind: typeof CstNodeKind.Include;
  path: string;
}

/**
 * Fill statement for constant port values.
 * Example: `fill saturation 0.8;`
 */
export interface ICstFill extends ICstNode {
  kind: typeof CstNodeKind.Fill;
  portName: string;
  value: number;
}

/**
 * Line comment.
 * Example: `// this is a comment`
 */
export interface ICstLineComment extends ICstNode {
  kind: typeof CstNodeKind.LineComment;
  text: string;
}

/**
 * Block comment.
 * Example: slash-star this is a comment star-slash
 */
export interface ICstBlockComment extends ICstNode {
  kind: typeof CstNodeKind.BlockComment;
  text: string;
}

/**
 * Serialize a CST back to source text (round-trip).
 */
export function serializeCst(node: ICstNode): string {
  // TODO: Implement full serialization
  void node;
  return '';
}
