/**
 * Port specifications for input and output ports.
 */

/**
 * Type alias for port type constraints.
 * Can be a single payload type name or array of names.
 */
export type AcceptsSpec = string | string[];

/**
 * Type alias for output port type.
 */
export type ProducesSpec = string;

/**
 * Count specification for channels.
 * - number: Fixed count
 * - [min, max]: Variable with bounds
 * - null: Variable with no bounds
 */
export type CountSpec = number | [number] | [number, number] | null;

/**
 * Parsed count specification.
 */
export interface IParsedCountSpec {
  fixedCount: number | null;
  minCount: number | null;
  maxCount: number | null;
}

/**
 * Parse a count specification into components.
 */
export function parseCountSpec(spec: CountSpec): IParsedCountSpec {
  if (spec === null) {
    return { fixedCount: null, minCount: null, maxCount: null };
  }
  if (typeof spec === "number") {
    return { fixedCount: spec, minCount: spec, maxCount: spec };
  }
  if (spec.length === 1) {
    return { fixedCount: null, minCount: spec[0], maxCount: null };
  }
  return { fixedCount: null, minCount: spec[0], maxCount: spec[1] };
}

/**
 * Input port specification options.
 */
export interface IInputPortSpecOptions {
  accepts: AcceptsSpec;
  count?: CountSpec;
}

/**
 * Input port specification.
 */
export class InputPortSpec {
  readonly accepts: AcceptsSpec;
  readonly count: CountSpec;
  readonly fixedCount: number | null;
  readonly minCount: number | null;
  readonly maxCount: number | null;

  constructor(options: IInputPortSpecOptions) {
    this.accepts = options.accepts;
    this.count = options.count ?? null;
    const parsed = parseCountSpec(this.count);
    this.fixedCount = parsed.fixedCount;
    this.minCount = parsed.minCount;
    this.maxCount = parsed.maxCount;
  }

  /**
   * Check if this port accepts a given payload type using a compatibility checker.
   *
   * @param producesType - The type string produced by the source port
   * @param isCompatible - Function to check if produces is compatible with accepts
   */
  acceptsPayloadType(producesType: string, isCompatible: (produces: string, accepts: string) => boolean): boolean {
    if (Array.isArray(this.accepts)) {
      return this.accepts.some((acceptType) => isCompatible(producesType, acceptType));
    }
    return isCompatible(producesType, this.accepts);
  }
}

/**
 * Output port specification options.
 */
export interface IOutputPortSpecOptions {
  produces: ProducesSpec;
  count?: CountSpec;
}

/**
 * Output port specification.
 */
export class OutputPortSpec {
  readonly produces: ProducesSpec;
  readonly count: CountSpec;
  readonly fixedCount: number | null;
  readonly minCount: number | null;
  readonly maxCount: number | null;

  constructor(options: IOutputPortSpecOptions) {
    this.produces = options.produces;
    this.count = options.count ?? null;
    const parsed = parseCountSpec(this.count);
    this.fixedCount = parsed.fixedCount;
    this.minCount = parsed.minCount;
    this.maxCount = parsed.maxCount;
  }
}
