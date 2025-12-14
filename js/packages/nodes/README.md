# @rasl/nodes

Built-in source, transform, and sink nodes for RASL.

## Overview

This package provides a standard library of nodes for common signal processing tasks in LED lighting and animation.

## Available Nodes

### Sources

#### WaveformNode

Generates configurable waveforms with per-channel phase and speed modulation.

```typescript
interface IWaveformConfig {
  id: string;
  shape?: WaveShape;        // 'sine' | 'triangle' | 'sawtooth' | 'attack_decay' | 'square'
  frequencyHz?: number;     // Default: 1.0
  outputChannels?: number;  // Default: 512
  attackRatio?: number;     // For attack_decay shape
  duty?: number;            // For square wave
}
```

**Inputs**: `phase` (optional), `speed` (optional)
**Outputs**: `out`

#### SeededRandomNode

Generates deterministic random values per channel.

```typescript
interface ISeededRandomConfig {
  id: string;
  seed?: number;
  outputChannels?: number;
  outputType?: OutputType;  // 'phase' | 'speed' | 'uniform' | 'binary'
  minSpeed?: number;
  maxSpeed?: number;
  density?: number;         // For binary output
}
```

**Outputs**: `out`

### Transforms

#### MathNode

Element-wise math operations on one or two inputs.

```typescript
interface IMathConfig {
  id: string;
  operation: MathOperation;  // 'add' | 'subtract' | 'multiply' | 'divide' | 'min' | 'max' | 'lerp' | 'screen'
  constantA?: number;        // Default value for input A
  constantB?: number;        // Default value for input B
  mix?: number;              // For lerp operation
  clamp?: boolean;           // Clamp output to 0-1
}
```

**Inputs**: `a`, `b`
**Outputs**: `out`

### Sinks

#### ConsoleSink

Debug output to console.

```typescript
interface IConsoleSinkConfig {
  id: string;
  fps?: number;
  format?: 'compact' | 'full' | 'hex';
  maxValues?: number;
}
```

**Inputs**: `in`

## Usage

```typescript
import { WaveformNode, MathNode, ConsoleSink } from '@rasl/nodes';

const sine = new WaveformNode({
  id: 'sine',
  shape: 'sine',
  frequencyHz: 0.5,
  outputChannels: 512,
});

const console = new ConsoleSink({
  id: 'debug',
  fps: 30,
  format: 'compact',
});
```

## Planned Nodes

- **ColorNode** - Color model conversion
- **ComposeNode** - Combine channels into color
- **ScaleBiasNode** - Linear transform (scale + offset)
- **ClampNode** - Clamp values to range
- **MapNode** - Remap value ranges
