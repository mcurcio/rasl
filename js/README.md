# RASL - Real-Time Animation Show Library (JavaScript)

A JavaScript/TypeScript implementation of RASL for building real-time animation graphs. Supports both Node.js server and browser environments.

## Packages

| Package                               | Description                                                          |
| ------------------------------------- | -------------------------------------------------------------------- |
| [@rasl/engine](./packages/engine)     | Runtime primitives, built-in nodes, graph builder, scheduler         |
| [@rasl/color](./packages/color)       | Color conversion + color-aware nodes (Compose, Literal, corrections) |
| [@rasl/lighting](./packages/lighting) | Network protocol nodes (sACN/E1.31, DDP)                             |
| [@rasl/config](./packages/config)     | Configuration parser and loader                                      |
| [@rasl/server](./packages/server)     | CLI/HTTP/WebSocket control server                                    |

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
import { GraphBuilder, UnifiedScheduler, WaveformNode } from "@rasl/engine";
import { ComposeNode, ColorNode } from "@rasl/color";
import { DdpSinkNode } from "@rasl/lighting";

// Build a graph
const builder = new GraphBuilder();
builder.addNode(new WaveformNode({ id: "wave", shape: "sine", frequencyHz: 0.5 }));
builder.addNode(new ComposeNode({ id: "color", outputType: "oklch" }));
builder.addNode(new ColorNode({ id: "rgb", model: "srgb" }));
builder.addNode(new DdpSinkNode({ id: "leds", host: "192.168.1.100", fps: 30 }));

builder.connect("wave", "out", "color", "lightness");
builder.connect("color", "out", "rgb", "in");
builder.connect("rgb", "out", "leds", "in");

// Run the scheduler
const plan = builder.build();
const scheduler = new UnifiedScheduler(plan);
await scheduler.run();
```

## Browser Support

Core packages (`@rasl/engine`, `@rasl/color`) work in browsers.
Lighting protocols (`@rasl/lighting`) require Node.js for UDP network access.

## License

MIT
