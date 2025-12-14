/**
 * Abstract Syntax Tree types for RASL config files.
 *
 * The AST represents the semantic structure of the configuration,
 * with resolved references and typed values.
 */

/**
 * Parsed document with nodes and connections.
 */
export interface IAstDocument {
  nodes: IAstNodeDef[];
  connections: IAstConnection[];
  includes: IAstInclude[];
}

/**
 * Resolved include directive.
 */
export interface IAstInclude {
  path: string;
  resolvedPath: string;
  document: IAstDocument | null;
}

/**
 * Node definition with type and properties.
 */
export interface IAstNodeDef {
  id: string;
  type: string;
  properties: Record<string, IAstProperty>;
}

/**
 * Resolved connection between ports.
 */
export interface IAstConnection {
  sourceNode: string;
  sourcePort: string;
  targetNode: string;
  targetPort: string;
  sourceSlice?: ISliceSpec;
  targetSlice?: ISliceSpec;
}

/**
 * Slice specification for channel ranges.
 */
export interface ISliceSpec {
  start: number;
  end: number | null;
}

/**
 * Typed property value.
 */
export interface IAstProperty {
  name: string;
  value: string | number | boolean | number[];
  type: 'string' | 'number' | 'boolean' | 'array';
}
