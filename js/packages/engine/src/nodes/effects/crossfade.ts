/**
 * CrossfadeNode - Crossfades between two inputs based on selector.
 */

import {
  BaseNode,
  Frame,
  InputPortSpec,
  type ITickContext,
  MatrixPayload,
  node,
  OutputPortSpec,
  PortGroup,
} from "../../runtime/index.js";

export interface ICrossfadeConfig {
  id: string;
  topic?: string;
}

@node("CrossfadeNode", "Crossfade")
export class CrossfadeNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    input0: new InputPortSpec({ accepts: ["matrix", "color"] }),
    input1: new InputPortSpec({ accepts: ["matrix", "color"] }),
    selector: new InputPortSpec({ accepts: "matrix" }),
  });

  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "matrix" }),
  });

  private readonly _topic: string;

  constructor(config: ICrossfadeConfig) {
    super(config);
    this._topic = config.topic ?? `crossfade.${this.id}`;
  }

  override async pull(tick: ITickContext): Promise<void> {
    const input0Port = this.inputs.get("input0");
    const input1Port = this.inputs.get("input1");
    const selectorPort = this.inputs.get("selector");

    const frame0 = input0Port?.read() ?? null;
    const frame1 = input1Port?.read() ?? null;
    const selectorFrame = selectorPort?.read() ?? null;

    if (!frame0 && !frame1) return;

    // Default to input0 if no selector
    let mix = 0.0;
    if (selectorFrame) {
      const selectorData = (selectorFrame.payload as MatrixPayload).flatten();
      mix = selectorData[0] ?? 0.0;
    }

    // Get data from both inputs
    const data0 = frame0 ? (frame0.payload as MatrixPayload).flatten() : null;
    const data1 = frame1 ? (frame1.payload as MatrixPayload).flatten() : null;

    const length = Math.max(data0?.length ?? 0, data1?.length ?? 0);
    const channels = frame0
      ? (frame0.payload as MatrixPayload).channels
      : frame1
        ? (frame1.payload as MatrixPayload).channels
        : 1;

    const outData = new Float32Array(length);
    for (let i = 0; i < length; i++) {
      const v0 = data0?.[i] ?? 0;
      const v1 = data1?.[i] ?? 0;
      outData[i] = v0 * (1 - mix) + v1 * mix;
    }

    const outPayload = new MatrixPayload(outData, channels);
    const outFrame = new Frame({
      topic: this._topic,
      timestamp: tick.wallTime,
      payload: outPayload,
      metadata: frame0?.metadata ?? frame1?.metadata,
    });

    this.outputs.get("out")?.write(outFrame);
  }
}
