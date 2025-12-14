/**
 * Node execution monitoring.
 */

/**
 * Execution statistics for a single node.
 */
export interface INodeStats {
  nodeId: string;
  invocations: number;
  successCount: number;
  failureCount: number;
  consecutiveFailures: number;
  totalTimeMs: number;
  avgTimeMs: number;
  maxTimeMs: number;
  lastError: Error | null;
}

/**
 * Monitor for tracking node execution statistics.
 */
export class NodeMonitor {
  private readonly _stats = new Map<string, IMutableNodeStats>();

  /**
   * Record a successful node invocation.
   */
  recordSuccess(nodeId: string, elapsedMs: number): void {
    const stats = this._getOrCreate(nodeId);
    stats.invocations++;
    stats.successCount++;
    stats.consecutiveFailures = 0;
    stats.totalTimeMs += elapsedMs;
    stats.maxTimeMs = Math.max(stats.maxTimeMs, elapsedMs);
  }

  /**
   * Record a failed node invocation.
   * Returns the new consecutive failure count.
   */
  recordFailure(nodeId: string, error: Error, elapsedMs: number): number {
    const stats = this._getOrCreate(nodeId);
    stats.invocations++;
    stats.failureCount++;
    stats.consecutiveFailures++;
    stats.totalTimeMs += elapsedMs;
    stats.lastError = error;
    return stats.consecutiveFailures;
  }

  /**
   * Get stats for a specific node.
   */
  getStats(nodeId: string): INodeStats | null {
    const stats = this._stats.get(nodeId);
    if (!stats) return null;
    return this._toNodeStats(stats);
  }

  /**
   * Get stats for all nodes.
   */
  getAllStats(): Map<string, INodeStats> {
    const result = new Map<string, INodeStats>();
    for (const [nodeId, stats] of this._stats) {
      result.set(nodeId, this._toNodeStats(stats));
    }
    return result;
  }

  /**
   * Reset all statistics.
   */
  reset(): void {
    this._stats.clear();
  }

  private _getOrCreate(nodeId: string): IMutableNodeStats {
    let stats = this._stats.get(nodeId);
    if (!stats) {
      stats = {
        nodeId,
        invocations: 0,
        successCount: 0,
        failureCount: 0,
        consecutiveFailures: 0,
        totalTimeMs: 0,
        maxTimeMs: 0,
        lastError: null,
      };
      this._stats.set(nodeId, stats);
    }
    return stats;
  }

  private _toNodeStats(stats: IMutableNodeStats): INodeStats {
    return {
      nodeId: stats.nodeId,
      invocations: stats.invocations,
      successCount: stats.successCount,
      failureCount: stats.failureCount,
      consecutiveFailures: stats.consecutiveFailures,
      totalTimeMs: stats.totalTimeMs,
      avgTimeMs: stats.invocations > 0 ? stats.totalTimeMs / stats.invocations : 0,
      maxTimeMs: stats.maxTimeMs,
      lastError: stats.lastError,
    };
  }
}

interface IMutableNodeStats {
  nodeId: string;
  invocations: number;
  successCount: number;
  failureCount: number;
  consecutiveFailures: number;
  totalTimeMs: number;
  maxTimeMs: number;
  lastError: Error | null;
}
