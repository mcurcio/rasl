/**
 * @rasl/engine runtime primitives.
 */

// Frame and metadata
export { EMPTY_METADATA, Frame, type IFrameConfig, type Metadata } from "./frame.js";

// Payloads
export {
  BoolPayload,
  FramePayload,
  type IFramePayload,
  type IPayloadDescriptor,
  MatrixPayload,
} from "./payloads/index.js";

// Ports
export {
  type AcceptsSpec,
  type CountSpec,
  EMPTY_INPUTS,
  EMPTY_OUTPUTS,
  InputPort,
  InputPortSpec,
  OutputPort,
  OutputPortSpec,
  PortGroup,
  type ProducesSpec,
} from "../nodes/ports/index.js";

// Nodes
export type { INode } from "../nodes/protocol.js";
export type { ILogger, LogFields } from "../nodes/context.js";
export { BaseNode } from "../nodes/base.js";
export { NodeContext } from "../nodes/context.js";
export { getInputs, getOutputs } from "../nodes/protocol.js";

// Tick context
export type { ITickContext } from "./tick.js";
export { createTickContext, getPullRate, pullRate } from "./tick.js";

// Registry
export {
  getNodeClass,
  getPayloadType,
  listNodeTypes,
  listPayloadTypes,
  node,
  payload,
  resetRegistries,
} from "../nodes/registry.js";

// Type compatibility
export {
  globalTypeRegistry,
  isTypeCompatible,
  type ITypeRegistry,
  registerDefaultTypes,
  TypeRegistry,
} from "./types/index.js";
