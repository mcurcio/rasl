/**
 * PortGroup - Named collection of ports.
 */

import { InputPort, OutputPort } from './port.js';
import { InputPortSpec, OutputPortSpec } from './spec.js';

/**
 * Empty ports singleton.
 */
export const EMPTY_PORTS = Object.freeze({
  names: [] as readonly string[],
  has: (_name: string) => false,
  get: (_name: string) => null,
  getDefault: () => ['', null] as const,
  [Symbol.iterator]: function* () {},
});

/**
 * Named collection of input or output ports.
 */
export class PortGroup {
  private readonly _ports: Map<string, InputPort | OutputPort>;
  private readonly _names: readonly string[];

  private constructor(ports: Map<string, InputPort | OutputPort>) {
    this._ports = ports;
    this._names = Object.freeze([...ports.keys()]);
  }

  /**
   * Create an input port group from specs.
   */
  static inputs(specs: Record<string, InputPortSpec>): PortGroup {
    const ports = new Map<string, InputPort>();
    for (const [name, spec] of Object.entries(specs)) {
      ports.set(name, new InputPort(name, spec));
    }
    return new PortGroup(ports);
  }

  /**
   * Create an output port group from specs.
   */
  static outputs(specs: Record<string, OutputPortSpec>): PortGroup {
    const ports = new Map<string, OutputPort>();
    for (const [name, spec] of Object.entries(specs)) {
      ports.set(name, new OutputPort(name, spec));
    }
    return new PortGroup(ports);
  }

  /**
   * Port names in this group.
   */
  get names(): readonly string[] {
    return this._names;
  }

  /**
   * Check if a port exists.
   */
  has(name: string): boolean {
    return this._ports.has(name);
  }

  /**
   * Get a port by name.
   */
  get(name: string): InputPort | OutputPort | null {
    return this._ports.get(name) ?? null;
  }

  /**
   * Get the default port (first port).
   */
  getDefault(): [string, InputPort | OutputPort | null] {
    const first = this._names[0];
    if (!first) return ['', null];
    return [first, this._ports.get(first) ?? null];
  }

  /**
   * Iterate over ports.
   */
  [Symbol.iterator](): Iterator<InputPort | OutputPort> {
    return this._ports.values();
  }
}
