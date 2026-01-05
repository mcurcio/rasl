/**
 * UI component prop types.
 */

import type { IGraphDescription, INodeStats } from "@rasl/engine";

/**
 * Graph view component props.
 */
export interface IGraphViewProps {
  graph: IGraphDescription;
  selectedNode?: string;
  onNodeSelect?: (nodeId: string) => void;
}

/**
 * Node inspector component props.
 */
export interface INodeInspectorProps {
  nodeId: string;
  stats: INodeStats | null;
  onParameterChange?: (param: string, value: unknown) => void;
}

/**
 * Performance panel component props.
 */
export interface IPerformancePanelProps {
  running: boolean;
  tickCount: number;
  uptime: number;
  nodeStats: Record<string, INodeStats>;
  frameBudgetMs?: number;
}

/**
 * Waveform display component props.
 */
export interface IWaveformDisplayProps {
  data: Float32Array | number[];
  width?: number;
  height?: number;
  color?: string;
  backgroundColor?: string;
}
