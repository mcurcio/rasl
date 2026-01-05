/**
 * Node protocol definition.
 *
 * Defines the Node interface that all DAG processing nodes must implement.
 */

import type { PortGroup } from "../ports/group.js";
import { EMPTY_INPUTS, EMPTY_OUTPUTS } from "../ports/group.js";
import type { InputPort, OutputPort } from "../ports/port.js";
import type { ITickContext } from "../tick.js";
import type { NodeContext } from "./context.js";

/**
 * Protocol defining the interface for all DAG processing nodes.
 *
 * Nodes are the fundamental processing units in the RASL graph.
 * They read from input ports, process data, and write to output ports.
 *
 * Node Categories:
 * - SourceNode: No inputs, generates frames (e.g., Waveform)
 * - TransformNode: Has both inputs and outputs
 * - SinkNode: No outputs, consumes frames
 *
 * Execution Model:
 * 1. start() is called when the scheduler begins
 * 2. pull() is called when the node needs to compute
 * 3. stop() is called during graceful shutdown
 */
export interface INode {
  /**
   * Unique node identifier within the graph.
   */
  readonly id: string;

  /**
   * Input ports (optional, omit for sources).
   */
  readonly inputs?: PortGroup<InputPort>;

  /**
   * Output ports (optional, omit for sinks).
   */
  readonly outputs?: PortGroup<OutputPort>;

  /**
   * Initialize the node when scheduler starts.
   */
  start(ctx: NodeContext): Promise<void>;

  /**
   * Process inputs and produce outputs.
   * Called by the scheduler when this node needs to compute.
   */
  pull(tick: ITickContext): Promise<void>;

  /**
   * Clean up the node during graceful shutdown.
   */
  stop(ctx: NodeContext): Promise<void>;
}

/**
 * Get node's input ports, defaulting to empty.
 */
export function getInputs(node: INode): PortGroup<InputPort> {
  return node.inputs ?? EMPTY_INPUTS;
}

/**
 * Get node's output ports, defaulting to empty.
 */
export function getOutputs(node: INode): PortGroup<OutputPort> {
  return node.outputs ?? EMPTY_OUTPUTS;
}
