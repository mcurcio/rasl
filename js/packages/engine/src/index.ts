/**
 * @rasl/engine - Graph builder, scheduler, and execution runtime
 *
 * This package provides the execution infrastructure for RASL graphs.
 */

// Runtime primitives (Frame, payloads, ports, node base/protocol, registry)
export * from './runtime/index.js';

// Built-in nodes (minimal standard library)
export * from './builtins/index.js';

// Graph building
export {
  GraphBuilder,
  ExecutionPlan,
  Edge,
  type IResolvedSlice,
  type IConnectOptions,
  type IGraphDescription,
  type INodeDescription,
  type IEdgeDescription,
} from './graph/index.js';

// Scheduler
export {
  UnifiedScheduler,
  type ISchedulerConfig,
  type INodeStats,
} from './scheduler/index.js';

// Logging
export * from './log/index.js';

export {
  loadRaslConfigFromSource,
  type IRaslLoadResult,
  type IRaslConfigError,
  type IRaslUiConfig,
} from './config/rasl.js';
