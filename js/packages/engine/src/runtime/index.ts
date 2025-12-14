/**
 * @rasl/engine runtime primitives.
 */

// Frame and metadata
export { Frame, type Metadata, EMPTY_METADATA, type IFrameConfig } from './frame.js';

// Payloads
export {
  FramePayload,
  type IPayloadDescriptor,
  type IFramePayload,
  MatrixPayload,
  BoolPayload,
} from './payloads/index.js';

// Ports
export {
  InputPortSpec,
  OutputPortSpec,
  InputPort,
  OutputPort,
  PortGroup,
  EMPTY_PORTS,
  type CountSpec,
  type AcceptsSpec,
  type ProducesSpec,
} from './ports/index.js';

// Nodes
export { BaseNode, NodeContext, getInputs, getOutputs } from './nodes/index.js';
export type { INode } from './nodes/index.js';
export type { ILogger, LogFields } from './nodes/index.js';

// Tick context
export { createTickContext, pullRate, getPullRate } from './tick.js';
export type { ITickContext } from './tick.js';

// Registry
export {
  node,
  payload,
  getNodeClass,
  getPayloadType,
  listNodeTypes,
  listPayloadTypes,
  ensureNodesLoaded,
  resetRegistries,
} from './registry.js';
