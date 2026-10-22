# API Ergonomics & Complexity

## Problem Statement

The TypeScript codebase has complex, inconsistent APIs that make it difficult to use and maintain. The APIs often require deep knowledge of internal implementation details and have poor developer experience.

## Current Issues

### 1. Logger API Overloading
**Location**: `packages/engine/src/log/index.ts`

**Problem**:
```typescript
interface ILogger {
  trace(a0: unknown, ...args: unknown[]): void;
  debug(a0: unknown, ...args: unknown[]): void;
  // Confusing overloads with different semantics
}
```

**Usage Issues**:
```typescript
// Is this fields + message? Or message + args?
logger.debug({ nodeId: "test" }, "Starting node");
logger.debug("Starting node", { nodeId: "test" });
// Both work but have different behavior!
```

**Impact**:
- Inconsistent usage patterns
- Poor IDE support
- Easy to make mistakes
- Hard to refactor

### 2. Node Configuration Inconsistency
**Locations**: 20+ different config interfaces

**Problem**:
```typescript
export interface IWaveformConfig {
  id: string;
  shape?: WaveShape;           // Optional
  frequencyHz?: number;        // Optional
  phase?: number;              // Optional
}

export interface ILiteralConfig {
  id: string;
  value: number[] | number[][];  // Required
  model?: string;              // Optional
}

export interface IRangeMapConfig {
  id: string;
  ranges: [number, number][];   // Required, complex type
  channelCount?: number;       // Optional
}
```

**Issues**:
- No consistent optional/required pattern
- Different naming conventions (frequencyHz vs channelCount)
- Complex nested types without helpers
- No validation at type level

### 3. Port Access Casting
**Location**: Throughout node implementations

**Problem**:
```typescript
const inPort = this.inputs.get("in") as InputPort;
const outPort = this.outputs.get("out") as OutputPort;
// Required casting everywhere
```

**Impact**:
- Verbose and error-prone
- No compile-time guarantee of port existence
- Easy to cast to wrong type

### 4. Frame Creation Verbosity
**Location**: Node implementations

**Problem**:
```typescript
const frame = new Frame({
  topic: this._topic,
  timestamp: performance.now() / 1000,
  payload: this._payload,
  metadata: EMPTY_METADATA,
});
```

**Issues**:
- Repetitive boilerplate
- Easy to forget metadata
- Manual timestamp calculation
- No builder pattern

## Proposed Solutions

### 1. Structured Logger API
**New Interface**:
```typescript
interface LogFields {
  nodeId?: string;
  tick?: number;
  elapsedMs?: number;
  [key: string]: unknown;
}

interface ILogger {
  trace(fields: LogFields, message?: string): void;
  debug(fields: LogFields, message?: string): void;
  info(fields: LogFields, message?: string): void;
  warn(fields: LogFields, message?: string): void;
  error(fields: LogFields & { err?: Error }, message?: string): void;
  
  // Convenience methods
  traceNode(nodeId: string, message: string, fields?: Omit<LogFields, 'nodeId'>): void;
  debugNode(nodeId: string, message: string, fields?: Omit<LogFields, 'nodeId'>): void;
}
```

**Benefits**:
- Clear field/message separation
- Better IDE support
- Type-safe field names
- Convenience methods

### 2. Unified Node Configuration
**Base Class**:
```typescript
abstract class BaseNodeConfig<TMetadata extends Record<string, unknown> = {}> {
  constructor(
    public readonly id: string,
    public readonly metadata?: TMetadata
  ) {}
}

// Specific configs extend base
export interface IWaveformConfig extends BaseNodeConfig<{
  version?: string;
}> {
  shape?: WaveShape;
  frequencyHz?: number;
  phase?: number;
}

// Helper for required fields
export interface RequiredConfig<T> {
  [K in keyof T]-?: T[K];
}
```

**Benefits**:
- Consistent base pattern
- Type-safe metadata
- Clear required vs optional
- Helper types for validation

### 3. Typed Port Access
**New PortGroup Methods**:
```typescript
class PortGroup<TPort extends Port> {
  // Existing method
  get(name: string): TPort | undefined;
  
  // New typed methods
  input<TName extends string>(name: TName): InputPort;
  output<TName extends string>(name: TName): OutputPort;
  
  // Optional access
  inputMaybe<TName extends string>(name: TName): InputPort | undefined;
  outputMaybe<TName extends string>(name: TName): OutputPort | undefined;
}

// Usage:
const inPort = this.inputs.input("in");  // No casting!
const outPort = this.outputs.output("out");
```

**Implementation**:
```typescript
input<TName extends string>(name: TName): InputPort {
  const port = this.get(name);
  if (!port) throw new Error(`Input port '${name}' not found`);
  return port as InputPort;
}
```

### 4. Frame Builder Pattern
**New Builder**:
```typescript
class FrameBuilder {
  private topic?: string;
  private timestamp?: number;
  private payload?: FramePayload;
  private metadata: Metadata = {};

  static create(): FrameBuilder {
    return new FrameBuilder();
  }

  topic(value: string): this {
    this.topic = value;
    return this;
  }

  timestamp(value?: number): this {
    this.timestamp = value ?? performance.now() / 1000;
    return this;
  }

  payload(value: FramePayload): this {
    this.payload = value;
    return this;
  }

  metadata(value: Metadata): this {
    this.metadata = { ...this.metadata, ...value };
    return this;
  }

  build(): Frame {
    if (!this.topic || !this.payload) {
      throw new Error("Frame requires topic and payload");
    }
    return new Frame({
      topic: this.topic,
      timestamp: this.timestamp!,
      payload: this.payload,
      metadata: this.metadata,
    });
  }
}

// Usage:
const frame = FrameBuilder.create()
  .topic(this._topic)
  .payload(this._payload)
  .metadata({ source: this.id })
  .build();
```

### 5. Configuration Validation
**Schema-based Validation**:
```typescript
interface ConfigSchema<T> {
  defaults?: Partial<T>;
  validate?: (config: T) => string | void;
  transform?: (config: Partial<T>) => T;
}

function createConfig<T>(
  schema: ConfigSchema<T>
): (raw: Partial<T>) => T {
  return (raw) => {
    const config = { ...schema.defaults, ...raw };
    
    if (schema.validate) {
      const error = schema.validate(config);
      if (error) throw new Error(error);
    }
    
    return schema.transform ? schema.transform(config) : config;
  };
}

// Usage:
const createWaveformConfig = createConfig<IWaveformConfig>({
  defaults: { shape: "sine", frequencyHz: 1.0 },
  validate: (config) => {
    if (config.frequencyHz && config.frequencyHz <= 0) {
      return "frequencyHz must be positive";
    }
  },
});
```

## Implementation Plan

### Phase 1: Logger API Redesign (High Priority)
1. Create new structured logger interface
2. Implement wrapper for backward compatibility
3. Update all call sites gradually
4. Deprecate old overloads

### Phase 2: Typed Port Access (High Priority)
1. Add typed methods to PortGroup
2. Update all node implementations
3. Add compile-time port existence checks
4. Remove casting throughout codebase

### Phase 3: Unified Config System (Medium Priority)
1. Create BaseNodeConfig class
2. Update all config interfaces
3. Add validation helpers
4. Update node constructors

### Phase 4: Frame Builder (Medium Priority)
1. Implement FrameBuilder class
2. Add convenience methods
3. Update all frame creation sites
4. Add tests for builder pattern

### Phase 5: Migration Tools (Low Priority)
1. Create codemod for logger migration
2. Add ESLint rules for new patterns
3. Update documentation and examples
4. Create migration guide

## Success Criteria

- [ ] Logger calls are type-safe and consistent
- [ ] No port casting required in node implementations
- [ ] All node configs follow consistent pattern
- [ ] Frame creation uses builder pattern
- [ ] Configuration validation at type level
- [ ] All tests pass with new APIs
- [ ] Developer experience improved

## Open Questions

1. Should we maintain backward compatibility during migration?
2. How to handle dynamic port names (e.g., indexed ports)?
3. Should config validation be runtime-only or compile-time too?
4. How to discover available ports for IDE support?
