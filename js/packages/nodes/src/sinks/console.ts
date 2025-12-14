/**
 * ConsoleSink - Debug output to console.
 */

import {
  BaseNode,
  Frame,
  MatrixPayload,
  PortGroup,
  InputPortSpec,
  type ITickContext,
  type NodeContext,
  node,
  pullRate,
} from '@rasl/engine';

export interface IConsoleSinkConfig {
  id: string;
  fps?: number;
  format?: 'compact' | 'full' | 'hex';
  maxValues?: number;
}

@node('ConsoleSink', 'Console')
export class ConsoleSink extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: ['matrix', 'color'] }),
  });

  private readonly _fps: number;
  private readonly _format: 'compact' | 'full' | 'hex';
  private readonly _maxValues: number;

  constructor(config: IConsoleSinkConfig) {
    super(config);
    this._fps = config.fps ?? 30;
    this._format = config.format ?? 'compact';
    this._maxValues = config.maxValues ?? 10;
  }

  override async start(ctx: NodeContext): Promise<void> {
    ctx.logger.info(`ConsoleSink '${this.id}' started at ${this._fps} FPS`);
  }

  @pullRate(30) // Will be overridden by config
  override async pull(tick: ITickContext): Promise<void> {
    const inPort = this.inputs.get('in');
    const frame = inPort ? (inPort as unknown as { read: () => Frame | null }).read() : null;
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.flatten();

    let output: string;
    switch (this._format) {
      case 'hex':
        output = this._formatHex(data);
        break;
      case 'full':
        output = this._formatFull(data);
        break;
      case 'compact':
      default:
        output = this._formatCompact(data);
    }

    console.log(`[${this.id}] t=${tick.t.toFixed(2)}s ${output}`);
  }

  private _formatCompact(data: Float32Array): string {
    const values = Array.from(data.slice(0, this._maxValues))
      .map((v) => v.toFixed(2))
      .join(', ');
    const suffix = data.length > this._maxValues ? ` ... (${data.length} total)` : '';
    return `[${values}${suffix}]`;
  }

  private _formatFull(data: Float32Array): string {
    return `[${Array.from(data).map((v) => v.toFixed(3)).join(', ')}]`;
  }

  private _formatHex(data: Float32Array): string {
    const hexValues = Array.from(data.slice(0, this._maxValues))
      .map((v) => Math.round(v * 255).toString(16).padStart(2, '0'))
      .join('');
    const suffix = data.length > this._maxValues ? `... (${data.length} total)` : '';
    return `#${hexValues} ${suffix}`;
  }
}
