/**
 * Registry for node and payload types.
 */

import type { BaseNode } from './nodes/base.js';
import type { FramePayload } from './payloads/base.js';

/**
 * Node class constructor type.
 */
export type NodeClass = new (config: any) => BaseNode;

/**
 * Payload class constructor type.
 */
export type PayloadClass = typeof FramePayload;

/**
 * Registry of node types.
 */
const nodeRegistry = new Map<string, NodeClass>();

/**
 * Registry of payload types.
 */
const payloadRegistry = new Map<string, PayloadClass>();

/**
 * Decorator to register a node class.
 */
export function node(typeName: string, alias?: string) {
  return function <T extends NodeClass>(target: T): T {
    nodeRegistry.set(typeName, target);
    if (alias) {
      nodeRegistry.set(alias, target);
    }
    return target;
  };
}

/**
 * Decorator to register a payload class.
 */
export function payload(typeName: string) {
  return function <T extends PayloadClass>(target: T): T {
    payloadRegistry.set(typeName, target);
    return target;
  };
}

/**
 * Get a registered node class by name.
 */
export function getNodeClass(typeName: string): NodeClass | undefined {
  return nodeRegistry.get(typeName);
}

/**
 * Get a registered payload class by name.
 */
export function getPayloadType(typeName: string): PayloadClass | undefined {
  return payloadRegistry.get(typeName);
}

/**
 * List all registered node type names.
 */
export function listNodeTypes(): string[] {
  return Array.from(nodeRegistry.keys());
}

/**
 * List all registered payload type names.
 */
export function listPayloadTypes(): string[] {
  return Array.from(payloadRegistry.keys());
}

/**
 * Reset registries (for testing).
 */
export function resetRegistries(): void {
  nodeRegistry.clear();
  payloadRegistry.clear();
}
