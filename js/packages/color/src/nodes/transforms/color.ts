/**
 * ColorNode - Universal color space converter.
 *
 * Converts any input to the specified color model.
 * Default output is sRGB.
 */

import {
  BaseNode,
  Frame,
  type ITickContext,
  InputPortSpec,
  MatrixPayload,
  OutputPortSpec,
  PortGroup,
  node,
} from '@rasl/engine';
import { convert, normalizeModel, type ColorModel } from '../../convert.js';

function payloadHasModel(payload: MatrixPayload): payload is MatrixPayload & { model: string } {
  return typeof (payload as { model?: unknown }).model === 'string';
}

export interface IColorConfig {
  id: string;
  model?: ColorModel;
  topic?: string;
}

@node('ColorNode', 'Color')
export class ColorNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: ['matrix', 'color'] }),
  });

  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: 'color' }),
  });

  private readonly _model: ColorModel;
  private readonly _topic: string;

  constructor(config: IColorConfig) {
    super(config);
    this._model = normalizeModel(config.model ?? 'srgb');
    this._topic = config.topic ?? `color.${this.id}`;
  }

  override async pull(tick: ITickContext): Promise<void> {
    const inPort = this.inputs.get('in');
    const frame = inPort?.read() ?? null;
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.flatten();
    const channels = payload.channels;

    // Determine source model from payload metadata or assume based on components
    let srcModel: ColorModel = 'srgb';
    if (payloadHasModel(payload)) {
      srcModel = normalizeModel(payload.model);
    }

    // Convert colors
    const numColors = Math.floor(data.length / channels);
    const outData = new Float32Array(numColors * 3);

    for (let i = 0; i < numColors; i++) {
      const offset = i * channels;
      const color: [number, number, number] = [
        data[offset] ?? 0,
        data[offset + 1] ?? 0,
        data[offset + 2] ?? 0,
      ];

      const converted = convert(color, srcModel, this._model);
      outData[i * 3] = converted[0];
      outData[i * 3 + 1] = converted[1];
      outData[i * 3 + 2] = converted[2];
    }

    const outPayload = new ColorPayload(outData, 3, this._model);

    const outFrame = new Frame({
      topic: this._topic,
      timestamp: tick.wallTime,
      payload: outPayload,
      metadata: frame.metadata,
    });

    this.outputs.get('out')?.write(outFrame);
  }
}

/**
 * ColorPayload - Matrix payload with color model tag.
 */
export class ColorPayload extends MatrixPayload {
  readonly model: ColorModel;

  constructor(data: Float32Array, components: number, model: ColorModel) {
    super(data, components);
    this.model = model;
  }

  override describe() {
    return {
      typeName: 'ColorPayload',
      domain: 'color',
      attrs: {
        model: this.model,
        count: this.count,
        channels: this.channels,
      },
    };
  }
}
