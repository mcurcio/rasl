# Missing Abstractions & Plugin System

## Problem Statement

The TypeScript codebase lacks key abstractions for extensibility, error handling, and metrics collection. This leads to tightly coupled code, manual registration patterns, and poor separation of concerns.

## Current Issues

### 1. No Plugin System for Nodes
**Location**: `packages/server/src/cli.ts`

**Problem**:
```typescript
// Manual registration in CLI
import { ColorNode, ComposeNode, CorrectionNode } from "@rasl/color";
import { DdpSinkNode, SacnSinkNode } from "@rasl/lighting";

// Hard-coded imports and registration
builder.registerNode(ColorNode);
builder.registerNode(ComposeNode);
builder.registerNode(CorrectionNode);
builder.registerNode(DdpSinkNode);
builder.registerNode(SacnSinkNode);
// Govee and LIFX nodes missing!
```

**Impact**:
- Adding new node types requires modifying core CLI
- Hardware-specific packages can't register themselves
- No runtime discovery of available nodes
- Tight coupling between server and node packages

### 2. Weak Error Boundaries
**Location**: Hardware sink implementations

**Problem**:
```typescript
// GoveeSink - just logs and continues
catch (error) {
  this._logger.error({ err: error }, "Govee connection failed");
  // No circuit breaker, no retry strategy
}

// LifxSink - removes client but no backoff
catch (error) {
  this._clients.delete(target);
  this._logger.error({ err: error }, `LIFX client failed: ${target}`);
}
```

**Impact**:
- No protection against cascading failures
- No exponential backoff for retries
- No way to disable failing components
- Poor resilience in production

### 3. Scattered Metrics Collection
**Location**: Throughout the codebase

**Problem**:
```typescript
// Scheduler has its own metrics
private _monitor = new NodeMonitor();

// Server has separate stats
const response: IStatsResponse = {
  running: this._running,
  tickCount: 0, // TODO: expose from scheduler
  uptime: (Date.now() - this._startTime) / 1000,
  nodes,
};

// Hardware nodes track their own metrics
this._framesSent++;
this._framesDropped++;
```

**Impact**:
- No unified metrics interface
- Metrics scattered across components
- Hard to get system-wide view
- No standard aggregation

### 4. No Event System
**Location**: Missing entirely

**Problem**:
- No way to react to node failures
- No system-wide event bus
- Components can't communicate loosely
- No hooks for monitoring/alerting

## Proposed Solutions

### 1. Plugin System Architecture
**Core Interfaces**:
```typescript
interface INodePlugin {
  readonly name: string;
  readonly version: string;
  readonly dependencies?: string[];
  
  register(registry: INodeRegistry): void;
  unregister?(registry: INodeRegistry): void;
}

interface INodeRegistry {
  registerNode<T extends INode>(
    nodeClass: new (config: any) => T,
    metadata?: NodeMetadata
  ): void;
  
  getNode(type: string): (new (config: any) => INode) | undefined;
  listNodes(): NodeMetadata[];
}

interface NodeMetadata {
  type: string;
  domain: string;
  description?: string;
  configSchema?: any;
}
```

**Plugin Discovery**:
```typescript
class PluginManager {
  private plugins = new Map<string, INodePlugin>();
  private registry: INodeRegistry;
  
  async loadPlugin(name: string): Promise<void> {
    try {
      const plugin = await import(name);
      if (plugin.default && this.isPlugin(plugin.default)) {
        plugin.default.register(this.registry);
        this.plugins.set(name, plugin.default);
      }
    } catch (error) {
      console.error(`Failed to load plugin ${name}:`, error);
    }
  }
  
  async loadPluginsFromConfig(config: string[]): Promise<void> {
    await Promise.all(config.map(name => this.loadPlugin(name)));
  }
}
```

**Auto-Registration**:
```typescript
// In @rasl/govee/index.ts
export default class GoveePlugin implements INodePlugin {
  readonly name = "@rasl/govee";
  readonly version = "1.0.0";
  
  register(registry: INodeRegistry): void {
    registry.registerNode(GoveeLightNode, {
      type: "govee",
      domain: "lighting",
      description: "Govee LAN RGB/RGBW lights",
    });
  }
}
```

### 2. Circuit Breaker Pattern
**Implementation**:
```typescript
interface ICircuitBreaker {
  execute<T>(fn: () => Promise<T>): Promise<T>;
  isOpen(): boolean;
  forceOpen(): void;
  forceClose(): void;
}

class CircuitBreaker implements ICircuitBreaker {
  private failures = 0;
  private lastFailure = 0;
  private state: "closed" | "open" | "half-open" = "closed";
  
  constructor(
    private options: {
      threshold: number;
      timeout: number;
      resetTimeout: number;
    }
  ) {}
  
  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === "open") {
      if (Date.now() - this.lastFailure > this.options.timeout) {
        this.state = "half-open";
      } else {
        throw new Error("Circuit breaker is open");
      }
    }
    
    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }
  
  private onSuccess(): void {
    this.failures = 0;
    this.state = "closed";
  }
  
  private onFailure(): void {
    this.failures++;
    this.lastFailure = Date.now();
    
    if (this.failures >= this.options.threshold) {
      this.state = "open";
    }
  }
}
```

**Usage in Hardware Nodes**:
```typescript
class GoveeLightNode extends BaseNode {
  private circuitBreaker: ICircuitBreaker;
  
  constructor(config: IGoveeConfig) {
    super(config);
    this.circuitBreaker = new CircuitBreaker({
      threshold: 5,
      timeout: 30000,  // 30 seconds
      resetTimeout: 60000,  // 1 minute
    });
  }
  
  override async pull(tick: ITickContext): Promise<void> {
    await this.circuitBreaker.execute(async () => {
      await this._sendColors();
    });
  }
}
```

### 3. Unified Metrics System
**Core Interface**:
```typescript
interface IMetrics {
  counter(name: string, value?: number): IMetrics;
  gauge(name: string, value: number): IMetrics;
  histogram(name: string, value: number): IMetrics;
  timer(name: string, duration: number): IMetrics;
  
  getSnapshot(): MetricsSnapshot;
  reset(): void;
}

interface MetricsSnapshot {
  counters: Record<string, number>;
  gauges: Record<string, number>;
  histograms: Record<string, HistogramData>;
  timers: Record<string, TimerData>;
}

class MetricsCollector implements IMetrics {
  private counters = new Map<string, number>();
  private gauges = new Map<string, number>();
  private histograms = new Map<string, number[]>();
  private timers = new Map<string, number[]>();
  
  counter(name: string, value = 1): this {
    this.counters.set(name, (this.counters.get(name) || 0) + value);
    return this;
  }
  
  gauge(name: string, value: number): this {
    this.gauges.set(name, value);
    return this;
  }
  
  // ... other methods
}
```

**Integration Points**:
```typescript
// Scheduler metrics
class UnifiedScheduler {
  constructor(plan: ExecutionPlan, config: ISchedulerConfig) {
    this.metrics = config.metrics ?? new MetricsCollector();
  }
  
  private async _executeNode(node: INode, tick: ITickContext): Promise<void> {
    const start = performance.now();
    try {
      await node.pull(tick);
      this.metrics.timer(`node.${node.id}.duration`, performance.now() - start);
      this.metrics.counter(`node.${node.id}.success`);
    } catch (error) {
      this.metrics.counter(`node.${node.id}.failure`);
      throw error;
    }
  }
}

// Hardware node metrics
class GoveeLightNode extends BaseNode {
  override async pull(tick: ITickContext): Promise<void> {
    try {
      await this._sendColors();
      this.metrics.counter("govee.frames_sent");
    } catch (error) {
      this.metrics.counter("govee.frames_dropped");
      throw error;
    }
  }
}
```

### 4. Event System
**Core Interface**:
```typescript
interface IEventBus {
  emit<T>(event: string, data: T): void;
  on<T>(event: string, handler: (data: T) => void): () => void;
  once<T>(event: string, handler: (data: T) => void): () => void;
  off(event: string, handler: Function): void;
}

class EventBus implements IEventBus {
  private listeners = new Map<string, Set<Function>>();
  
  emit<T>(event: string, data: T): void {
    const handlers = this.listeners.get(event);
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler(data);
        } catch (error) {
          console.error(`Event handler error for ${event}:`, error);
        }
      });
    }
  }
  
  on<T>(event: string, handler: (data: T) => void): () => void {
    const handlers = this.listeners.get(event) ?? new Set();
    handlers.add(handler);
    this.listeners.set(event, handlers);
    
    return () => this.off(event, handler);
  }
  
  // ... other methods
}
```

**Standard Events**:
```typescript
// System events
interface SystemEvents {
  "node.started": { nodeId: string; timestamp: number };
  "node.stopped": { nodeId: string; timestamp: number };
  "node.failed": { nodeId: string; error: Error; timestamp: number };
  "scheduler.started": { timestamp: number };
  "scheduler.stopped": { timestamp: number; duration: number };
}

// Hardware events
interface HardwareEvents {
  "connection.established": { target: string; protocol: string };
  "connection.lost": { target: string; protocol: string; error?: Error };
  "connection.restored": { target: string; protocol: string };
}
```

## Implementation Plan

### Phase 1: Plugin System (High Priority)
1. Define plugin interfaces
2. Implement PluginManager
3. Update @rasl/govee and @rasl/lifx with plugins
4. Update server CLI to use PluginManager
5. Add plugin discovery from config

### Phase 2: Circuit Breaker (High Priority)
1. Implement ICircuitBreaker interface
2. Add to hardware sink nodes
3. Add configuration options
4. Add circuit breaker metrics

### Phase 3: Unified Metrics (Medium Priority)
1. Create IMetrics interface and implementation
2. Integrate with scheduler
3. Update hardware nodes
4. Add metrics aggregation
5. Update server stats endpoint

### Phase 4: Event System (Medium Priority)
1. Implement EventBus
2. Define standard events
3. Add event emission in key places
4. Create monitoring/alerting examples
5. Add event persistence options

### Phase 5: Documentation & Examples (Low Priority)
1. Write plugin development guide
2. Create example plugins
3. Add monitoring examples
4. Update API documentation

## Success Criteria

- [ ] New node packages can register without CLI changes
- [ ] Hardware failures don't cascade through system
- [ ] All metrics available through unified interface
- [ ] System events can be monitored and reacted to
- [ ] Backward compatibility maintained
- [ ] Performance impact minimal (<5%)

## Open Questions

1. Should plugins be loaded at startup or dynamically?
2. How to handle plugin version conflicts?
3. Should circuit breakers be configurable per node?
4. How to persist metrics across restarts?
5. Should events be persisted for replay?
