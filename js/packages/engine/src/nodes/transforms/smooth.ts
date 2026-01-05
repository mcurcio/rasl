/**
 * Frame smoothing transform node.
 *
 * Exponentially smooths incoming frames with optional slew limiting.
 */

import { BaseNode, InputPortSpec, MatrixPayload, node, OutputPortSpec, PortGroup } from "../../runtime/index.js";
import type { ITickContext } from "../../runtime/tick.js";

/**
 * Configuration for SmoothNode.
 */
export interface ISmoothConfig {
  id: string;
  /** Response time in seconds (0 disables smoothing) */
  smoothPeriod?: number;
  /** Maximum allowed per-frame change per component (0 disables) */
  maxDelta?: number;
  /** If difference is below this threshold, reuse previous output */
  bypassEpsilon?: number;
}

/**
 * Transform node that exponentially smooths incoming frames.
 *
 * The node keeps an accumulator per channel, blends new samples in with an
 * exponential moving average, and emits the smoothed payload. A `reset` port
 * can clear parts (or all) of the accumulator so the next frame passes
 * through unchanged.
 */
@node("SmoothNode", "Smooth")
export class SmoothNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    input: new InputPortSpec({ accepts: "matrix" }),
    reset: new InputPortSpec({ accepts: ["matrix", "bool"] }),
  });

  readonly outputs = PortGroup.outputs({
    output: new OutputPortSpec({ produces: "matrix" }),
  });

  private readonly _tauSeconds: number;
  private readonly _maxDelta: number;
  private readonly _bypassEpsilon: number;
  private _state: Float32Array | null = null;
  private _stateChannels = 0;

  constructor(config: ISmoothConfig) {
    super({ id: config.id });
    this._tauSeconds = config.smoothPeriod ?? 0.05; // 50ms default
    this._maxDelta = config.maxDelta ?? 0;
    this._bypassEpsilon = config.bypassEpsilon ?? 0;
  }

  override async pull(tick: ITickContext): Promise<void> {
    const inputPort = this.inputs.get("input");
    if (!inputPort) return;

    const frame = inputPort.read();
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.data;
    const channels = payload.channels;

    // Ensure state buffer exists and matches shape
    const [state, initialized] = this._ensureState(data, channels);

    // Check for reset signal
    const resetPort = this.inputs.get("reset");
    const resetFrame = resetPort?.read();
    const resetPayload = resetFrame?.payload as MatrixPayload | undefined;
    const resetMask = this._extractResetMask(resetPayload, data.length);
    let resetApplied = false;

    if (resetMask) {
      for (let i = 0; i < data.length; i++) {
        if (resetMask[i]) {
          state[i] = data[i];
        }
      }
      resetApplied = true;
    }

    // Compute output
    let outputData: Float32Array;
    if (initialized && !resetApplied) {
      outputData = new Float32Array(state);
    } else {
      outputData = this._blend(state, data, tick.dt);
    }

    const newPayload = new MatrixPayload(outputData, channels);
    const outputPort = this.outputs.get("output");
    if (outputPort) {
      outputPort.write(frame.withPayload(newPayload));
    }
  }

  private _blend(state: Float32Array, target: Float32Array, dt: number): Float32Array {
    const delta = new Float32Array(target.length);
    for (let i = 0; i < target.length; i++) {
      delta[i] = target[i] - state[i];
    }

    // Check bypass epsilon
    if (this._bypassEpsilon > 0) {
      let maxDiff = 0;
      for (let i = 0; i < delta.length; i++) {
        maxDiff = Math.max(maxDiff, Math.abs(delta[i]));
      }
      if (maxDiff <= this._bypassEpsilon) {
        return new Float32Array(state);
      }
    }

    const alpha = this._computeAlpha(dt);

    if (alpha <= 0) {
      return new Float32Array(state);
    }

    // Apply alpha
    if (alpha < 1) {
      for (let i = 0; i < delta.length; i++) {
        delta[i] *= alpha;
      }
    }

    // Apply max delta clamp
    if (this._maxDelta > 0) {
      for (let i = 0; i < delta.length; i++) {
        delta[i] = Math.max(-this._maxDelta, Math.min(this._maxDelta, delta[i]));
      }
    }

    // Update state and return copy
    for (let i = 0; i < state.length; i++) {
      state[i] += delta[i];
    }

    return new Float32Array(state);
  }

  private _computeAlpha(dt: number): number {
    if (this._tauSeconds <= 0) {
      return 1;
    }
    if (dt <= 0) {
      return 0;
    }
    return 1 - Math.exp(-dt / this._tauSeconds);
  }

  private _ensureState(data: Float32Array, channels: number): [Float32Array, boolean] {
    if (this._state === null || this._state.length !== data.length || this._stateChannels !== channels) {
      this._state = new Float32Array(data);
      this._stateChannels = channels;
      return [this._state, true];
    }
    return [this._state, false];
  }

  private _extractResetMask(payload: MatrixPayload | null | undefined, length: number): Uint8Array | null {
    if (!payload) return null;

    const raw = payload.data;
    if (raw.length === 0) return null;

    // Single value: if non-zero, reset all
    if (raw.length === 1) {
      if (raw[0] === 0) return null;
      const mask = new Uint8Array(length);
      mask.fill(1);
      return mask;
    }

    // Build mask from raw values
    const mask = new Uint8Array(length);
    let anySet = false;
    for (let i = 0; i < length; i++) {
      const srcIdx = i < raw.length ? i : i % raw.length;
      if (raw[srcIdx] !== 0) {
        mask[i] = 1;
        anySet = true;
      }
    }

    return anySet ? mask : null;
  }
}
