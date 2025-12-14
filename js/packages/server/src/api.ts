/**
 * REST API response types for RASL server.
 */

import type { IGraphDescription, INodeStats } from '@rasl/engine';

/**
 * Health check response.
 */
export interface IHealthResponse {
  status: 'ok' | 'error';
  version: string;
  uptime: number;
}

/**
 * Graph description response.
 */
export interface IGraphResponse {
  graph: IGraphDescription;
}

/**
 * Node details response.
 */
export interface INodeResponse {
  id: string;
  type: string;
  inputs: string[];
  outputs: string[];
  stats: INodeStats | null;
}

/**
 * Execution statistics response.
 */
export interface IStatsResponse {
  running: boolean;
  tickCount: number;
  uptime: number;
  nodes: Record<string, INodeStats>;
}
