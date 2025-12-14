/**
 * Parser for nginx-style config files.
 *
 * Supports:
 * - Round-tripping hooks (whitespace/comments) as a future extension
 * - Line comments (//) and block comments (/* *​/)
 * - Optional trailing semicolons
 */
import type { ICstDocument } from './cst.js';
/**
 * Parse error with location information.
 */
export interface IParseError {
    message: string;
    line: number;
    column: number;
    span?: {
        start: number;
        end: number;
    };
}
/**
 * Parser configuration options.
 */
export interface IParseConfig {
    /**
     * Whether to preserve trivia (whitespace/comments) in CST.
     * Default: true (for round-tripping support)
     */
    preserveTrivia?: boolean;
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
export declare function parse(source: string, config?: IParseConfig): IParseResult;
/**
 * Parse a RASL config file with async include resolution.
 *
 * @param source - The config file source text
 * @param config - Parser configuration with includeResolver
 * @returns Promise resolving to parse result with resolved includes
 */
export declare function parseAsync(source: string, config?: IParseConfig): Promise<IParseResult>;
//# sourceMappingURL=parser.d.ts.map