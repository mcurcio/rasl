# Performance Optimization & Drains

## Problem Statement

The TypeScript codebase has several performance drains and inefficiencies that will impact real-time performance, especially at scale with complex graphs and high frame rates.

## Current Issues

### 1. Excessive `any` Casting
**Locations**: Throughout codebase, especially tests and scheduler

**Problem**:
```typescript
// 20+ instances like this:
(logger as any)[level](fields, msg);
(RecordingSink.prototype.pull as any)[PULL_RATE_SYMBOL] = 60;
payload: { describe: () => ({ typeName: "Custom", domain: "custom", attrs: {} }) } as any
```

**Impact**:
- Bypasses TypeScript optimization
- Runtime type checking overhead
- Poor developer experience and refactoring safety

### 2. Dynamic Prototype Inspection
**Location**: `packages/engine/src/scheduler/unified.ts:271-273`

**Problem**:
```typescript
const proto = Object.getPrototypeOf(node);
const pullMethod = proto?.pull;
const hz = getPullRate(pullMethod, node);
```

**Impact**:
- Expensive runtime reflection
- Happens on every sink lookup
- Prevents JIT optimization

### 3. Unnecessary Object Creation
**Locations**: Logger, frame creation, context objects

**Problem**:
- New logger instances created frequently
- Frame objects created even when unchanged
- Context objects allocated per tick

**Impact**:
- GC pressure at high frame rates
- Memory allocation overhead
- Cache misses

### 4. Inefficient Loop Structure
**Location**: `packages/engine/src/scheduler/unified.ts:199-215`

**Problem**:
```typescript
while (this._running && performance.now() < endTime) {
  const now = performance.now() / 1000;  // Called every iteration
  // ... 
  await this._sleep(1);  // Unnecessary async overhead
}
```

**Impact**:
- Excessive system calls
- Async overhead in tight loop
- Poor CPU utilization

## Proposed Solutions

### 1. Eliminate `any` Casting
**Approach**:
- Create proper interfaces for dynamic metadata
- Use type guards instead of casting
- Implement symbol-based metadata system

**Example Fix**:
```typescript
// Instead of:
(RecordingSink.prototype.pull as any)[PULL_RATE_SYMBOL] = 60;

// Use:
interface IPullRateMetadata {
  [PULL_RATE_SYMBOL]?: number;
}
(RecordingSink.prototype.pull as IPullRateMetadata)[PULL_RATE_SYMBOL] = 60;
```

### 2. Static Pull Rate Registry
**New System**:
```typescript
class NodeRegistry {
  private static pullRates = new Map<string, number>();
  
  static registerPullRate(nodeClass: Function, hz: number): void {
    this.pullRates.set(nodeClass.name, hz);
  }
  
  static getPullRate(node: INode): number | undefined {
    return this.pullRates.get(node.constructor.name);
  }
}
```

**Benefits**:
- O(1) lookup instead of prototype traversal
- No runtime reflection
- JIT-friendly

### 3. Object Pooling
**Implement Pools For**:
- Frame objects (recycle with new payload)
- Logger instances (reuse child loggers)
- Context objects (reset and reuse)

**Example**:
```typescript
class FramePool {
  private pool: Frame[] = [];
  
  acquire(topic: string, timestamp: number, payload: FramePayload): Frame {
    const frame = this.pool.pop() || new Frame({ topic, timestamp, payload });
    frame.reset(topic, timestamp, payload);
    return frame;
  }
  
  release(frame: Frame): void {
    this.pool.push(frame);
  }
}
```

### 4. Efficient Scheduler Loop
**Redesign**:
```typescript
async runFor(durationMs: number): Promise<void> {
  const endTime = performance.now() + durationMs;
  const startTime = performance.now() / 1000;
  
  // Pre-calculate frame times
  const frameInterval = 1000 / 60; // 60 FPS target
  let nextFrameTime = 0;
  
  while (this._running && performance.now() < endTime) {
    const now = performance.now();
    
    if (now >= nextFrameTime) {
      const t = (now / 1000) - startTime;
      await this.processFrame(t);
      nextFrameTime = now + frameInterval;
    } else {
      // Busy wait for precise timing
      await new Promise(resolve => setTimeout(resolve, 1));
    }
  }
}
```

## Implementation Plan

### Phase 1: Remove `any` Casting (High Priority)
1. Create proper interfaces for all dynamic metadata
2. Update all logger implementations
3. Fix test code casting
4. Add lint rule to prevent new `any` usage

### Phase 2: Static Registry System (High Priority)
1. Implement `NodeRegistry` class
2. Add decorator for automatic registration
3. Update scheduler to use registry
4. Remove prototype inspection code

### Phase 3: Object Pooling (Medium Priority)
1. Create pool interfaces and implementations
2. Pool Frame objects
3. Pool Context objects
4. Pool Logger child instances

### Phase 4: Scheduler Optimization (Medium Priority)
1. Redesign main loop for efficiency
2. Implement frame-based timing
3. Remove unnecessary async overhead
4. Add performance benchmarks

## Performance Targets

### Before Optimization
- 60 FPS with 10 nodes: ~15ms/frame
- Memory allocation: ~1MB/second
- GC pauses: 5-10ms every 2 seconds

### After Optimization
- 60 FPS with 10 nodes: ~8ms/frame
- Memory allocation: ~100KB/second
- GC pauses: <2ms every 5 seconds

## Success Criteria

- [ ] Zero `any` casts in production code
- [ ] No prototype inspection in hot paths
- [ ] Object pooling for Frame and Context
- [ ] Scheduler loop optimized for 60+ FPS
- [ ] Performance benchmarks passing
- [ ] Memory usage stable over time

## Open Questions

1. Should object pooling be configurable (enable/disable for debugging)?
2. How to measure and report performance regressions?
3. Should we implement a custom allocator for TypedArrays?
