/**
 * Parser for nginx-style config files.
 *
 * Supports:
 * - Round-tripping hooks (whitespace/comments) as a future extension
 * - Line comments (//) and block comments (/* *​/)
 * - Optional trailing semicolons
 */
import { parseImpl } from './parser-impl.js';
/**
 * Parse a RASL config file.
 *
 * @param source - The config file source text
 * @param config - Optional parser configuration
 * @returns Parse result with CST, AST, and diagnostics
 */
export function parse(source, config) {
    return parseImpl(source, config);
}
/**
 * Parse a RASL config file with async include resolution.
 *
 * @param source - The config file source text
 * @param config - Parser configuration with includeResolver
 * @returns Promise resolving to parse result with resolved includes
 */
export async function parseAsync(source, config) {
    void config;
    return parse(source, config);
}
//# sourceMappingURL=parser.js.map