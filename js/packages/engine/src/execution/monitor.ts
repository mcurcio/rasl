export interface INodeStats {
  nodeId: string;
  pullCount: number;
  errorCount: number;
  consecutiveErrors: number;
  lastError: string | null;
  lastFrameTimeMs: number;
  avgFrameTimeMs: number;
}

export class NodeMonitor {
  private readonly _stats = new Map<string, INodeStats>();

  recordSuccess(nodeId: string, elapsedMs: number): void {
    const stats = this._getOrCreate(nodeId);
    stats.pullCount++;
    stats.consecutiveErrors = 0;
    stats.lastFrameTimeMs = elapsedMs;
    stats.avgFrameTimeMs =
      stats.pullCount === 1 ? elapsedMs : stats.avgFrameTimeMs + (elapsedMs - stats.avgFrameTimeMs) / stats.pullCount;
  }

  recordFailure(nodeId: string, error: Error, elapsedMs: number): number {
    const stats = this._getOrCreate(nodeId);
    stats.errorCount++;
    stats.consecutiveErrors++;
    stats.lastError = error.message;
    stats.lastFrameTimeMs = elapsedMs;
    return stats.consecutiveErrors;
  }

  getStats(nodeId: string): INodeStats | null {
    return this._stats.get(nodeId) ?? null;
  }

  getAllStats(): Map<string, INodeStats> {
    return new Map(this._stats);
  }

  private _getOrCreate(nodeId: string): INodeStats {
    let stats = this._stats.get(nodeId);
    if (!stats) {
      stats = {
        nodeId,
        pullCount: 0,
        errorCount: 0,
        consecutiveErrors: 0,
        lastError: null,
        lastFrameTimeMs: 0,
        avgFrameTimeMs: 0,
      };
      this._stats.set(nodeId, stats);
    }
    return stats;
  }
}
