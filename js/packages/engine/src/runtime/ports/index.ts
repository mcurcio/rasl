/**
 * Port types for the RASL runtime.
 */

export {
  InputPortSpec,
  OutputPortSpec,
  parseCountSpec,
  type AcceptsSpec,
  type ProducesSpec,
  type CountSpec,
  type IParsedCountSpec,
  type IInputPortSpecOptions,
  type IOutputPortSpecOptions,
} from './spec.js';

export { InputPort, OutputPort } from './port.js';
export { PortGroup, EMPTY_INPUTS, EMPTY_OUTPUTS } from './group.js';
