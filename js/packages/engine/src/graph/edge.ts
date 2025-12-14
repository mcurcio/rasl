/**
 * Edge - Immutable connection between node ports.
 */

/**
 * Resolved channel slice with start and optional end.
 */
export interface IResolvedSlice {
  readonly start: number;
  readonly end: number | null;
}

/**
 * Options for connecting ports.
 */
export interface IConnectOptions {
  sourceSlice?: IResolvedSlice;
  targetSlice?: IResolvedSlice;
  repeat?: number;
}

/**
 * Immutable edge connecting an output port to an input port.
 */
export class Edge {
  readonly source: string;
  readonly sourcePort: string;
  readonly target: string;
  readonly targetPort: string;
  readonly sourceSlice: IResolvedSlice | null;
  readonly targetSlice: IResolvedSlice | null;
  readonly repeat: number;

  constructor(
    source: string,
    sourcePort: string,
    target: string,
    targetPort: string,
    options?: IConnectOptions
  ) {
    this.source = source;
    this.sourcePort = sourcePort;
    this.target = target;
    this.targetPort = targetPort;
    this.sourceSlice = options?.sourceSlice ?? null;
    this.targetSlice = options?.targetSlice ?? null;
    this.repeat = options?.repeat ?? 1;
  }

  /**
   * Calculate the length of a slice given a fixed count.
   */
  static sliceLength(slice: IResolvedSlice, fixedCount: number | null): number | null {
    if (fixedCount === null) return null;
    const end = slice.end ?? fixedCount;
    return end - slice.start;
  }
}
