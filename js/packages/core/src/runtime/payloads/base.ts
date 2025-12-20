/**
 * Base payload types for the RASL frame system.
 *
 * Defines the abstract base class for all payload types
 * and the PayloadDescriptor for introspection.
 */

/**
 * Introspection metadata for any payload.
 */
export interface IPayloadDescriptor {
  typeName: string;
  domain: string;
  attrs: Record<string, unknown>;
}

export interface IFramePayload {
  describe(): IPayloadDescriptor;
}

/**
 * Abstract base for all payload types.
 */
export abstract class FramePayload {
  /**
   * Domain identifier for this payload type.
   */
  static readonly domain = 'payload' as string;

  /**
   * Number of components per element (e.g., 3 for RGB).
   */
  static readonly components: number | null = null;

  /**
   * Get introspection metadata for this payload.
   */
  abstract describe(): IPayloadDescriptor;

  /**
   * Check if `other` type can be accepted by ports expecting this class.
   * Default: standard subclass check.
   */
  static isCompatibleWith(other: typeof FramePayload): boolean {
    return other.prototype instanceof this || other === this;
  }

  /**
   * Ensure a writable backing buffer exists and is large enough.
   */
  static ensureBuffer(
    buffer: Float32Array | null,
    count: number,
    components: number
  ): Float32Array {
    if (count < 0) {
      throw new Error(`count must be non-negative, got ${count}`);
    }
    if (components <= 0) {
      throw new Error(`components must be > 0, got ${components}`);
    }

    const requiredSize = count * components;
    if (buffer === null || buffer.length < requiredSize) {
      return new Float32Array(requiredSize);
    }
    return buffer;
  }
}
