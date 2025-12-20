/**
 * Tick context and scheduling primitives for RASL.
 *
 * Provides the timing context passed to nodes during pull execution,
 * and the pullRate decorator for declaring sink frame rates.
 */

/**
 * Timing information for the current scheduler tick.
 *
 * Passed to pull() methods. Immutable - represents a single moment in time.
 */
export interface ITickContext {
  /**
   * Monotonic tick counter since scheduler start.
   */
  readonly tick: number;

  /**
   * Time since scheduler start (seconds).
   */
  readonly t: number;

  /**
   * Time since this node was last invoked (seconds).
   */
  readonly dt: number;

  /**
   * Monotonic wall clock time for this tick.
   */
  readonly wallTime: number;
}

/**
 * Create a TickContext.
 */
export function createTickContext(options: {
  tick: number;
  t: number;
  dt: number;
  wallTime: number;
}): ITickContext {
  return Object.freeze(options);
}

/**
 * Symbol for storing pull rate on methods.
 */
export const PULL_RATE_SYMBOL = Symbol('pullRate');

/**
 * Decorator declaring that a node drives the scheduler at a specific rate.
 *
 * Apply to a node's pull() method to indicate it should be invoked at
 * the specified frequency. Only sinks typically use this decorator.
 *
 * @param hz - Frequency in Hz, or function returning Hz
 */
export function pullRate(hz: number | ((self: unknown) => number)) {
  return function (
    _target: unknown,
    _propertyKey: string,
    descriptor: TypedPropertyDescriptor<any>
  ): TypedPropertyDescriptor<any> {
    if (descriptor.value) {
      (descriptor.value as Record<symbol, unknown>)[PULL_RATE_SYMBOL] = hz;
    }
    return descriptor;
  };
}

/**
 * Get the pull rate from a method, if decorated.
 */
export function getPullRate(method: unknown, instance?: unknown): number | null {
  const hz = (method as Record<symbol, unknown>)?.[PULL_RATE_SYMBOL];
  if (hz === undefined) return null;
  if (typeof hz === 'function') {
    return hz(instance);
  }
  return hz as number;
}
