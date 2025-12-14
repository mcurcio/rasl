/**
 * Parser for RASL config files.
 *
 * Supports:
 * - Round-tripping with whitespace and comment preservation
 * - Line comments (//) and block comments (/* *​/)
 * - Optional trailing semicolons (only required between directives on same line)
 * - Include directive with async resolver
 */

import type { ICstDocument } from './cst.js';
import type { IAstDocument } from './ast.js';

/**
 * Parse error with location information.
 */
export interface IParseError {
  message: string;
  line: number;
  column: number;
  span?: { start: number; end: number };
}

/**
 * Include resolver function type.
 * Given an include path, returns the file contents.
 */
export type IncludeResolver = (path: string) => Promise<string>;

/**
 * Parser configuration options.
 */
export interface IParseConfig {
  /**
   * Async function to resolve include directives.
   * If not provided, includes will be recorded but not resolved.
   */
  includeResolver?: IncludeResolver;

  /**
   * Base path for resolving relative includes.
   */
  basePath?: string;

  /**
   * Whether to preserve trivia (whitespace/comments) in CST.
   * Default: true (for round-tripping support)
   */
  preserveTrivia?: boolean;

  /**
   * Maximum include depth to prevent circular includes.
   * Default: 10
   */
  maxIncludeDepth?: number;
}

/**
 * Result of parsing a config file.
 */
export interface IParseResult {
  /**
   * Concrete Syntax Tree (preserves all source info for round-tripping).
   */
  cst: ICstDocument | null;

  /**
   * Abstract Syntax Tree (semantic structure with resolved references).
   */
  ast: IAstDocument | null;

  /**
   * Parse errors that prevent successful parsing.
   */
  errors: IParseError[];

  /**
   * Warnings that don't prevent parsing but indicate potential issues.
   */
  warnings: IParseError[];

  /**
   * Source text (for round-tripping verification).
   */
  source: string;
}

/**
 * Parse a RASL config file.
 *
 * @param source - The config file source text
 * @param config - Optional parser configuration
 * @returns Parse result with CST, AST, and diagnostics
 */
export function parse(source: string, config?: IParseConfig): IParseResult {
  // TODO: Implement full parser
  void config; // Suppress unused warning

  return {
    cst: null,
    ast: null,
    errors: [],
    warnings: [],
    source,
  };
}

/**
 * Parse a RASL config file with async include resolution.
 *
 * @param source - The config file source text
 * @param config - Parser configuration with includeResolver
 * @returns Promise resolving to parse result with resolved includes
 */
export async function parseAsync(
  source: string,
  config: IParseConfig & { includeResolver: IncludeResolver }
): Promise<IParseResult> {
  // TODO: Implement async parsing with include resolution
  void config;

  return {
    cst: null,
    ast: null,
    errors: [],
    warnings: [],
    source,
  };
}
