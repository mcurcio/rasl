# @rasl/ui

Web UI components for RASL monitoring and control.

## Overview

This package provides a web-based interface for:

- Real-time graph visualization
- Node state monitoring
- Performance metrics display
- Parameter adjustment

## Key Components

### GraphView

Displays the node graph with connections and data flow.

```typescript
interface IGraphViewProps {
  graph: IGraphDescription;
  selectedNode?: string;
  onNodeSelect?: (nodeId: string) => void;
}
```

### NodeInspector

Shows details for a selected node including inputs, outputs, and stats.

```typescript
interface INodeInspectorProps {
  nodeId: string;
  stats: INodeStats | null;
  onParameterChange?: (param: string, value: unknown) => void;
}
```

### PerformancePanel

Displays real-time performance metrics.

```typescript
interface IPerformancePanelProps {
  stats: IStatsResponse;
  frameBudgetMs?: number;
}
```

### WaveformDisplay

Visualizes numeric array data as a waveform.

```typescript
interface IWaveformDisplayProps {
  data: Float32Array | number[];
  width?: number;
  height?: number;
  color?: string;
}
```

## Static Assets

The `public/` directory contains:

- `index.html` - Main HTML entry point
- `styles.css` - Base styles
- `app.js` - Client-side JavaScript

## Usage

The UI is served by `@rasl/server` and connects via WebSocket for real-time updates.

```typescript
import { RaslServer } from '@rasl/server';

const server = new RaslServer({
  port: 8080,
  staticDir: '@rasl/ui/public',
});
```

## Development

```bash
pnpm dev  # Start Vite dev server
```
