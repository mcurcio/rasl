/**
 * Runtime port instances.
 */

import type { Frame } from "../../runtime/frame.js";
import type { InputPortSpec, OutputPortSpec } from "./spec.js";

/**
 * Runtime input port.
 */
export class InputPort {
  readonly name: string;
  readonly spec: InputPortSpec;

  private _frame: Frame | null = null;
  private _hasUpstream = false;

  constructor(name: string, spec: InputPortSpec) {
    this.name = name;
    this.spec = spec;
  }

  /**
   * Read the current frame from this port.
   */
  read(): Frame | null {
    return this._frame;
  }

  /**
   * Check if this port has an upstream connection.
   */
  hasUpstream(): boolean {
    return this._hasUpstream;
  }

  /**
   * Internal: Set the frame for this port.
   */
  _setFrame(frame: Frame | null): void {
    this._frame = frame;
  }

  /**
   * Internal: Mark whether this port has upstream.
   */
  _setHasUpstream(value: boolean): void {
    this._hasUpstream = value;
  }

  /**
   * Internal: Clear the frame.
   */
  _clear(): void {
    this._frame = null;
  }
}

/**
 * Runtime output port.
 */
export class OutputPort {
  readonly name: string;
  readonly spec: OutputPortSpec;

  private _frame: Frame | null = null;

  constructor(name: string, spec: OutputPortSpec) {
    this.name = name;
    this.spec = spec;
  }

  /**
   * Write a frame to this port.
   */
  write(frame: Frame): void {
    this._frame = frame;
  }

  /**
   * Internal: Consume the written frame.
   */
  _consume(): Frame | null {
    const frame = this._frame;
    this._frame = null;
    return frame;
  }

  /**
   * Internal: Clear the frame.
   */
  _clear(): void {
    this._frame = null;
  }
}
