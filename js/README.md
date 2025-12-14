# RASL - Real-Time Animation Show Library (JavaScript)

A JavaScript/TypeScript implementation of RASL for building real-time animation graphs. Supports both Node.js server and browser environments.

## Packages

| Package | Description |
|---------|-------------|
| [@rasl/core](./packages/core) | Core types, Frame, ports, and base node abstractions |
| [@rasl/engine](./packages/engine) | Graph builder, scheduler, and execution runtime |
| [@rasl/nodes](./packages/nodes) | Built-in source, transform, and sink nodes |
| [@rasl/color](./packages/color) | Color conversion (sRGB, OKLCH, OkHSL, etc.) |
| [@rasl/config](./packages/config) | Configuration parser and loader |
| [@rasl/e131](./packages/e131) | sACN/E1.31 protocol support (Node.js only) |
| [@rasl/ddp](./packages/ddp) | DDP protocol support (Node.js only) |

## Architecture

RASL uses a **pull-based DAG execution model**:

1. **Sinks** drive the scheduler at their configured frame rate
2. **Scheduler** pulls data through the graph from sinks to sources
3. **Nodes** compute on-demand when their outputs are requested
4. **Frames** flow through typed ports with channel-level routing

```text
Sources → Transforms → Sinks
   ↑          ↑          ↑
   └──────────┴──────────┘
        Pull direction
```

## Quick Start

```bash
# Install dependencies
pnpm install

# Build all packages
pnpm build

# Run tests
pnpm test
```

## Usage

```typescript
import { GraphBuilder, UnifiedScheduler } from '@rasl/engine';
import { WaveformNode, ComposeNode, ColorNode } from '@rasl/nodes';
import { DdpSink } from '@rasl/ddp';

// Build a graph
const builder = new GraphBuilder();
builder.addNode(new WaveformNode({ id: 'wave', shape: 'sine', frequencyHz: 0.5 }));
builder.addNode(new ComposeNode({ id: 'color', outputType: 'oklch' }));
builder.addNode(new ColorNode({ id: 'rgb', model: 'srgb' }));
builder.addNode(new DdpSink({ id: 'leds', host: '192.168.1.100', fps: 30 }));

builder.connect('wave', 'out', 'color', 'lightness');
builder.connect('color', 'out', 'rgb', 'in');
builder.connect('rgb', 'out', 'leds', 'in');

// Run the scheduler
const plan = builder.build();
const scheduler = new UnifiedScheduler(plan);
await scheduler.run();
```

## Browser Support

Core packages (`@rasl/core`, `@rasl/engine`, `@rasl/nodes`, `@rasl/color`) work in browsers.
Protocol packages (`@rasl/e131`, `@rasl/ddp`) require Node.js for network access.

## License

MIT
