/**
 * @rasl/engine - Graph builder, scheduler, and execution runtime
 *
 * This package provides the execution infrastructure for RASL.
 */

// Core domain - the fundamental entities
export type { IEngine, IEngineConfig } from "./core/engine.js";
export type { IGraph, IGraphConfig } from "./core/graph.js";
export type { IEngineStats, IGraphStats } from "./core/stats.js";
export { Engine } from "./core/engine.js";

// Execution domain - graph execution machinery
export type { ExecutionPlan, IGraphDescription, INodeDescription, IEdgeDescription } from "./execution/plan.js";
export type { Edge, IConnectOptions, IResolvedSlice } from "./execution/edge.js";
export type { UnifiedScheduler, ISchedulerConfig, INodeStats } from "./execution/scheduler.js";
export { ExecutionPlan as ExecutionPlanImpl } from "./execution/plan.js";
export { GraphBuilder } from "./execution/builder.js";
export { UnifiedScheduler as SchedulerImpl } from "./execution/scheduler.js";

// Node domain - all node-related functionality
export type { ILogger, LogFields } from "./nodes/index.js";
export type { INode } from "./nodes/index.js";
export type { NodeClass, PayloadClass } from "./nodes/index.js";
export { BaseNode, NodeContext, getNodeClass, getPayloadType, node, payload } from "./nodes/index.js";
export type { PortGroup, InputPort, OutputPort } from "./nodes/ports/index.js";

// Runtime infrastructure - platform concerns
export type { Frame, Metadata } from "./runtime/frame.js";
export type { ITickContext } from "./runtime/tick.js";
export type { FramePayload, MatrixPayload, BoolPayload } from "./runtime/payloads/index.js";

// Logging domain
export type { IEngineLoggerConfig, LogLevel } from "./logging/index.js";
export { createEngineLogger, createConsoleLogger, childLogger } from "./logging/index.js";

// Config loading
export { loadRaslConfigFromSource } from "./config/rasl.js";
export type { IRaslLoadResult, IRaslUiConfig } from "./config/rasl.js";
