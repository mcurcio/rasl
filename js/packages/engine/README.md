# @rasl/engine

Graph builder, scheduler, and execution runtime for RASL (Real-Time Animation Show Library).

## Overview

This package provides the execution infrastructure for RASL graphs:

- **GraphBuilder**: Assembles nodes and edges into an ExecutionPlan
- **ExecutionPlan**: Compiled graph ready for runtime execution
- **UnifiedScheduler**: Pull-based scheduler that drives graph execution
- **Edge**: Immutable connection between node ports

## Installation

```bash
pnpm add @rasl/engine
```

## Usage

### Building a Graph

```typescript
import { GraphBuilder, WaveformNode } from '@rasl/engine';
import { ColorNode } from '@rasl/color';

const builder = new GraphBuilder();

// Add nodes
builder.addNode(new WaveformNode({ id: 'wave', shape: 'sine' }));
builder.addNode(new ColorNode({ id: 'color', model: 'srgb' }));

// Connect ports
builder.connect('wave', 'out', 'color', 'lightness');

// Build execution plan
const plan = builder.build();
```

### Running the Scheduler

```typescript
import { UnifiedScheduler } from '@rasl/engine';

const scheduler = new UnifiedScheduler(plan);

// Run until stopped
await scheduler.run();

// Or run for a specific duration
await scheduler.runFor(10_000); // 10 seconds
```

### Inspecting the Graph

```typescript
// Get graph description
const description = plan.describe();
console.log(description.nodes);
console.log(description.edges);
console.log(description.topologicalOrder);
```

## Key Concepts

### Pull-Based Execution

RASL uses a pull-based execution model:

1. **Sinks** declare their frame rate via `@pullRate` decorator
2. **Scheduler** wakes sinks at their requested rate
3. **Sinks** pull data from upstream nodes
4. **Nodes** compute on-demand when their outputs are requested

### Topological Ordering

The GraphBuilder computes a topological order for nodes, ensuring:
- Sources are started before transforms
- Transforms are started before sinks
- Cycles are detected and warned about (but allowed)

### Channel Slicing

Edges can include channel slices for partial port connections:

```typescript
builder.connect('source', 'out', 'sink', 'in', {
  sourceSlice: { start: 0, end: 150 },
  targetSlice: { start: 0, end: 150 },
});
```

## API Reference

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed API documentation.
