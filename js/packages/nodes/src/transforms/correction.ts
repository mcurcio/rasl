/**
 * ColorCorrectionNode - Per-LED-type color correction.
 *
 * Applies gamma, saturation, brightness, and RGB channel scaling
 * corrections in linear RGB space for physically correct results.
 */

import {
  BaseNode,
  Frame,
  MatrixPayload,
  PortGroup,
  InputPortSpec,
  OutputPortSpec,
  type ITickContext,
  node,
} from '@rasl/engine';

export interface IColorCorrectionConfig {
  id: string;
  gamma?: number;
  saturation?: number;
  brightness?: number;
  rScale?: number;
  gScale?: number;
  bScale?: number;
  rOffset?: number;
  gOffset?: number;
  bOffset?: number;
  topic?: string;
}

@node('ColorCorrectionNode', 'ColorCorrection')
export class ColorCorrectionNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: ['matrix', 'color'] }),
  });

  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: 'color' }),
  });

  private readonly _gamma: number;
  private readonly _saturation: number;
  private readonly _brightness: number;
  private readonly _rgbScale: Float32Array;
  private readonly _rgbOffset: Float32Array;
  private readonly _topic: string;

  constructor(config: IColorCorrectionConfig) {
    super(config);
    this._gamma = config.gamma ?? 2.2;
    this._saturation = config.saturation ?? 1.0;
    this._brightness = config.brightness ?? 1.0;
    this._rgbScale = new Float32Array([
      config.rScale ?? 1.0,
      config.gScale ?? 1.0,
      config.bScale ?? 1.0,
    ]);
    this._rgbOffset = new Float32Array([
      config.rOffset ?? 0.0,
      config.gOffset ?? 0.0,
      config.bOffset ?? 0.0,
    ]);
    this._topic = config.topic ?? `correction.${this.id}`;
  }

  override async pull(tick: ITickContext): Promise<void> {
    const inPort = this.inputs.get('in');
    const frame = inPort
      ? (inPort as unknown as { read: () => Frame | null }).read()
      : null;
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.flatten();

    // Validate: must be RGB triplets
    if (data.length % 3 !== 0) {
      const outPort = this.outputs.get('out');
      if (outPort) {
        (outPort as unknown as { write: (f: Frame) => void }).write(frame);
      }
      return;
    }

    const numPixels = Math.floor(data.length / 3);
    const output = new Float32Array(data.length);

    for (let i = 0; i < numPixels; i++) {
      const idx = i * 3;

      // Get RGB values (assume sRGB input)
      let r = data[idx];
      let g = data[idx + 1];
      let b = data[idx + 2];

      // Step 1: Convert sRGB to linear (remove gamma 2.2)
      r = Math.pow(Math.max(0, r), 2.2);
      g = Math.pow(Math.max(0, g), 2.2);
      b = Math.pow(Math.max(0, b), 2.2);

      // Step 2: Apply RGB channel scaling (white balance)
      r = r * this._rgbScale[0] + this._rgbOffset[0];
      g = g * this._rgbScale[1] + this._rgbOffset[1];
      b = b * this._rgbScale[2] + this._rgbOffset[2];

      // Step 3: Apply saturation adjustment (in linear space)
      if (this._saturation !== 1.0) {
        // Compute luminance (Rec. 709 coefficients for linear RGB)
        const luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;
        // Lerp between grayscale and color
        r = luma + this._saturation * (r - luma);
        g = luma + this._saturation * (g - luma);
        b = luma + this._saturation * (b - luma);
      }

      // Step 4: Apply brightness
      if (this._brightness !== 1.0) {
        r *= this._brightness;
        g *= this._brightness;
        b *= this._brightness;
      }

      // Step 5: Clamp to valid range before gamma
      r = Math.max(0, Math.min(1, r));
      g = Math.max(0, Math.min(1, g));
      b = Math.max(0, Math.min(1, b));

      // Step 6: Apply output gamma
      if (this._gamma !== 1.0) {
        const invGamma = 1.0 / this._gamma;
        r = Math.pow(r, invGamma);
        g = Math.pow(g, invGamma);
        b = Math.pow(b, invGamma);
      }

      output[idx] = r;
      output[idx + 1] = g;
      output[idx + 2] = b;
    }

    const outPayload = new MatrixPayload(output, 3);
    const outFrame = new Frame({
      topic: this._topic,
      timestamp: tick.wallTime,
      payload: outPayload,
      metadata: frame.metadata,
    });

    const outPort = this.outputs.get('out');
    if (outPort) {
      (outPort as unknown as { write: (f: Frame) => void }).write(outFrame);
    }
  }
}
