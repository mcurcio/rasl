# @rasl/lighting

Lighting protocol sinks for RASL, supporting industry-standard protocols for LED control.

## Supported Protocols

### E1.31 (sACN)
Streaming ACN - ANSI E1.31 protocol for DMX over IP.

- Multicast and unicast support
- Multiple universe output
- Priority and synchronization

### DDP (Distributed Display Protocol)
Lightweight protocol for addressable LED control.

- Push-based data transfer
- Large channel counts (up to 480 channels per packet)
- Low latency

## Key Types

### E1.31 Sink

```typescript
interface IE131SinkConfig {
  id: string;
  universe: number;
  priority?: number;
  fps?: number;
  multicast?: boolean;
  destinationIp?: string;
}
```

### DDP Sink

```typescript
interface IDdpSinkConfig {
  id: string;
  host: string;
  port?: number;
  fps?: number;
  offset?: number;
}
```

## Usage

```typescript
import { E131Sink, DdpSink } from '@rasl/lighting';

// E1.31 output to universe 1
const e131 = new E131Sink({
  id: 'sacn_out',
  universe: 1,
  priority: 100,
  fps: 44,
});

// DDP output to a controller
const ddp = new DdpSink({
  id: 'ddp_out',
  host: '192.168.1.100',
  port: 4048,
  fps: 44,
});
```

## Network Requirements

- E1.31: UDP port 5568 (multicast: 239.255.x.x)
- DDP: UDP port 4048 (configurable)
