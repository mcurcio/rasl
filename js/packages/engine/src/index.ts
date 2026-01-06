/**
 * @rasl/engine - Graph builder, scheduler, and execution runtime
 *
 * This package provides the execution infrastructure for/**
 * RASL Engine package exports
 */

// Core types and interfaces
export type { ILogger, LogFields, NodeContext } from "./runtime/nodes/index.js";
export type { INode, BaseNode } from "./runtime/nodes/base.js";
export type { Frame, Payload, Metadata } from "./runtime/frame.js";
export type { PortGroup, InputPort, OutputPort } from "./runtime/ports/index.js";

// Graph types
export type { ExecutionPlan, IGraphDescription, INodeDescription, IEdgeDescription } from "./graph/plan.js";
export type { Edge, IConnectOptions, IResolvedSlice } from "./graph/edge.js";
export { GraphBuilder } from "./graph/builder.js";

// Scheduler
export type { ISchedulerConfig, INodeStats } from "./scheduler/unified.js";
export { UnifiedScheduler } from "./scheduler/unified.js";

// Logging
export type { IEngineLoggerConfig, LogLevel } from "./log/index.js";
export { createEngineLogger, createConsoleLogger } from "./log/index.js";

// Engine (top-level)
export type { IEngine, IEngineConfig, IGraph, IGraphConfig, IEngineStats, IGraphStats } from "./engine/index.js";
export { Engine } from "./engine/index.js";

// Config loading
export { loadRaslConfigFromSource } from "./config/rasl.js";
export type { IRaslLoadResult, IRaslUiConfig } from "./config/rasl.js";
