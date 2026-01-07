/**
 * Statistics and monitoring interfaces
 */

export interface IEngineStats {
  /** Total number of graphs managed by the engine */
  totalGraphs: number;
  /** Number of graphs currently running */
  runningGraphs: number;
  /** Total number of nodes across all graphs */
  totalNodes: number;
  /** Engine uptime in milliseconds */
  uptimeMs: number;
}

export interface IGraphStats {
  /** Number of nodes in this graph */
  nodeCount: number;
  /** Current frame rate */
  currentFps: number;
  /** Frames processed since start */
  framesProcessed: number;
  /** Average frame time in milliseconds */
  avgFrameTimeMs: number;
}
