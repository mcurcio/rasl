/**
 * Port types for the RASL runtime.
 */

export { EMPTY_INPUTS, EMPTY_OUTPUTS, PortGroup } from "./group.js";
export { InputPort, OutputPort } from "./port.js";
export {
  type AcceptsSpec,
  type CountSpec,
  type IInputPortSpecOptions,
  InputPortSpec,
  type IOutputPortSpecOptions,
  type IParsedCountSpec,
  OutputPortSpec,
  parseCountSpec,
  type ProducesSpec,
} from "./spec.js";
