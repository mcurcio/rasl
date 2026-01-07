/**
 * Node domain exports
 * 
 * All node-related functionality: base classes, implementations, ports, and registry.
 */

// Core node infrastructure
export { BaseNode } from "./base.js";
export type { ILogger, LogFields } from "./context.js";
export { NodeContext } from "./context.js";
export { getInputs, getOutputs, type INode } from "./protocol.js";

// Node registry and discovery
export type { NodeClass, PayloadClass } from "./registry.js";
export { getNodeClass, getPayloadType, node, payload } from "./registry.js";

// Port system
export * from "./ports/index.js";

// Built-in node implementations
export * from "./sources/index.js";
export * from "./transforms/index.js";
export * from "./sinks/index.js";
export * from "./effects/index.js";
