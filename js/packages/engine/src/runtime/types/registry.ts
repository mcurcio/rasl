/**
 * TypeRegistry - String-based payload type compatibility resolver.
 *
 * Supports:
 * - Colon-delimited hierarchy (e.g., "color:rgb:linear" is subtype of "color:rgb" and "color")
 * - Explicit inheritance edges (e.g., "color" inherits from "matrix")
 * - Package/user extensibility via registerInheritance()
 */

import { ErrorCodes, RaslError } from "../../errors.js";

/**
 * Interface for type registry operations.
 */
export interface ITypeRegistry {
  /**
   * Register an inheritance edge: childType inherits from parentType.
   */
  registerInheritance(childType: string, parentType: string): void;

  /**
   * Check if produces type is compatible with accepts type.
   */
  isCompatible(produces: string, accepts: string): boolean;

  /**
   * Get all parent types (direct and transitive) for a given type.
   */
  getParents(typeName: string): readonly string[];
}

/**
 * TypeRegistry implementation.
 */
export class TypeRegistry implements ITypeRegistry {
  /**
   * Map from child type to set of direct parent types.
   */
  readonly #inheritanceEdges = new Map<string, Set<string>>();

  /**
   * Cache for transitive parent lookups.
   */
  readonly #parentCache = new Map<string, readonly string[]>();

  /**
   * Register an inheritance edge: childType inherits from parentType.
   *
   * @throws RaslError if this would create a cycle
   */
  registerInheritance(childType: string, parentType: string): void {
    if (childType === parentType) {
      throw new RaslError(ErrorCodes.InvalidArgument, `Cannot register self-inheritance: "${childType}"`);
    }

    // Check for cycles: if parentType already inherits from childType, this would create a cycle
    const parentAncestors = this.getParents(parentType);
    if (parentAncestors.includes(childType)) {
      throw new RaslError(
        ErrorCodes.InvalidArgument,
        `Inheritance cycle detected: "${childType}" -> "${parentType}" would create a cycle`,
      );
    }

    let edges = this.#inheritanceEdges.get(childType);
    if (!edges) {
      edges = new Set();
      this.#inheritanceEdges.set(childType, edges);
    }
    edges.add(parentType);

    // Invalidate cache
    this.#parentCache.clear();
  }

  /**
   * Check if produces type is compatible with accepts type.
   */
  isCompatible(produces: string, accepts: string): boolean {
    // Exact match
    if (produces === accepts) {
      return true;
    }

    // Check colon-prefix hierarchy: "color:rgb:linear" is compatible with "color:rgb" and "color"
    if (this.#isPrefixOf(accepts, produces)) {
      return true;
    }

    // Check inheritance edges (including transitive)
    const parents = this.getParents(produces);
    for (const parent of parents) {
      if (parent === accepts || this.#isPrefixOf(accepts, parent)) {
        return true;
      }
    }

    // Check if any prefix of produces has inheritance that matches
    const prefixes = this.#getPrefixes(produces);
    for (const prefix of prefixes) {
      const prefixParents = this.getParents(prefix);
      for (const parent of prefixParents) {
        if (parent === accepts || this.#isPrefixOf(accepts, parent)) {
          return true;
        }
      }
    }

    return false;
  }

  /**
   * Get all parent types (direct and transitive) for a given type.
   */
  getParents(typeName: string): readonly string[] {
    const cached = this.#parentCache.get(typeName);
    if (cached) {
      return cached;
    }

    const parents = new Set<string>();
    const visited = new Set<string>();
    this.#collectParents(typeName, parents, visited);

    const result = Array.from(parents);
    this.#parentCache.set(typeName, result);
    return result;
  }

  /**
   * Recursively collect all parent types.
   */
  #collectParents(typeName: string, parents: Set<string>, visited: Set<string>): void {
    if (visited.has(typeName)) {
      return;
    }
    visited.add(typeName);

    const directParents = this.#inheritanceEdges.get(typeName);
    if (directParents) {
      for (const parent of directParents) {
        parents.add(parent);
        this.#collectParents(parent, parents, visited);
      }
    }
  }

  /**
   * Check if `prefix` is a colon-prefix of `full`.
   * "color" is prefix of "color:rgb" but not of "colorful".
   */
  #isPrefixOf(prefix: string, full: string): boolean {
    if (!full.startsWith(prefix)) {
      return false;
    }
    // Must be exact match or followed by ":"
    return full.length === prefix.length || full[prefix.length] === ":";
  }

  /**
   * Get all colon-prefixes of a type string.
   * "color:rgb:linear" -> ["color:rgb", "color"]
   */
  #getPrefixes(typeName: string): string[] {
    const prefixes: string[] = [];
    let idx = typeName.lastIndexOf(":");
    while (idx > 0) {
      prefixes.push(typeName.substring(0, idx));
      idx = typeName.lastIndexOf(":", idx - 1);
    }
    return prefixes;
  }
}

/**
 * Global type registry instance.
 * Packages register their inheritance edges here.
 */
export const globalTypeRegistry = new TypeRegistry();

/**
 * Whether default types have been registered.
 */
let defaultsRegistered = false;

/**
 * Ensure default types are registered before use.
 * Called internally by isTypeCompatible.
 */
function ensureDefaults(): void {
  if (!defaultsRegistered) {
    registerDefaultTypes();
  }
}

/**
 * Register default RASL type hierarchy.
 * - color inherits from matrix (colors are numeric matrices)
 * - bool inherits from matrix (booleans are 0/1 matrices)
 *
 * This is called lazily on first use to avoid circular import issues.
 */
export function registerDefaultTypes(registry: ITypeRegistry = globalTypeRegistry): void {
  if (registry === globalTypeRegistry && defaultsRegistered) {
    return;
  }
  registry.registerInheritance("color", "matrix");
  registry.registerInheritance("bool", "matrix");
  if (registry === globalTypeRegistry) {
    defaultsRegistered = true;
  }
}

/**
 * Check if a producer type is compatible with an acceptor type.
 *
 * Compatibility rules:
 * 1. Exact match: "color" is compatible with "color"
 * 2. Prefix hierarchy: "color:rgb" is compatible with "color"
 * 3. Inheritance: if "color" inherits from "matrix", then "color" is compatible with "matrix"
 * 4. Transitive: if A inherits B and B inherits C, then A is compatible with C
 *
 * @param produces - The type string produced by an output port
 * @param accepts - The type string accepted by an input port
 * @param registry - Optional TypeRegistry for inheritance lookup (uses global if not provided)
 * @returns true if produces is compatible with accepts
 */
export function isTypeCompatible(produces: string, accepts: string, registry?: ITypeRegistry): boolean {
  if (registry === undefined) {
    ensureDefaults();
  }
  const reg = registry ?? globalTypeRegistry;
  return reg.isCompatible(produces, accepts);
}
