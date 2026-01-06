# Type System Weaknesses & Improvements

## Problem Statement

The TypeScript codebase has several type system weaknesses that reduce compile-time safety, require runtime validation, and make it difficult to extend the system safely.

## Current Issues

### 1. Runtime Type Checking Everywhere
**Location**: Throughout the codebase

**Problem**:
```typescript
// Instead of TypeScript guards, we have runtime checks
function parseUniverses(universes: unknown): number[] {
  if (typeof universes === "number") return [universes];
  if (Array.isArray(universes)) return universes.map(Number);
  return [1];
}

function parseFps(fps: unknown): number {
  if (typeof fps === "number") return fps;
  if (typeof fps === "string") {
    // Handle "20hz", "30", "50ms" formats
    const match = fps.match(/^(\d+)(hz|ms)?$/i);
    if (match) {
      const value = parseInt(match[1], 10);
      return match[2]?.toLowerCase() === "ms" ? 1000 / value : value;
    }
  }
  return 30;
}
```

**Impact**:
- No compile-time guarantees
- Runtime overhead for validation
- Easy to make mistakes in validation logic
- Poor IDE support

### 2. Weak Payload Type System
**Location**: `packages/engine/src/runtime/payloads/`

**Problem**:
```typescript
export abstract class FramePayload {
  static readonly domain = "payload" as string;
  
  // No compile-time domain safety
  static isCompatibleWith(other: typeof FramePayload): boolean {
    return other.prototype instanceof this || other === this;
  }
  
  // No generic constraints
  abstract describe(): IPayloadDescriptor;
}

// Usage requires casting
const payload = frame.payload as MatrixPayload;
```

**Impact**:
- No compile-time domain checking
- Payload types can be mixed incorrectly
- Runtime validation required everywhere
- Difficult to add new payload types safely

### 3. Missing Branded Types
**Location**: Throughout the codebase

**Problem**:
```typescript
// Numbers lose their semantic meaning
interface IWaveformConfig {
  frequencyHz?: number;  // Could be any number
  phase?: number;       // Could be frequency in disguise
}

interface ISchedulerConfig {
  frameBudgetMs?: number;  // Could be milliseconds or seconds
}

// Easy to mix up:
node.frequency = config.frameBudgetMs;  // Wrong units!
```

**Impact**:
- Unit mixing errors
- No compile-time validation of units
- Poor API safety
- Runtime bugs from unit confusion

### 4. Loose Configuration Types
**Location**: Node configuration interfaces

**Problem**:
```typescript
// No validation at type level
export interface ILiteralConfig {
  id: string;
  value: number[] | number[][];  // Could be invalid nested structure
  model?: string;                // Could be any string
}

// Runtime validation required
constructor(config: ILiteralConfig) {
  super({ id: config.id });
  // Need to validate config.value shape at runtime
  if (Array.isArray(config.value) && config.value.length > 0) {
    if (Array.isArray(config.value[0])) {
      // 2D array
    } else {
      // 1D array
    }
  }
}
```

**Impact**:
- Configuration errors only caught at runtime
- Complex validation logic in constructors
- Poor developer experience
- Hard to document valid configurations

## Proposed Solutions

### 1. Compile-Time Type Guards
**Replace Runtime Checks with Generics**:
```typescript
// Instead of unknown, use proper types
type UniverseSpec = number | number[] | `${number}u${number}`;
type FpsSpec = number | `${number}hz` | `${number}ms`;

// Type-safe parsers
type ParseUniverses<T extends UniverseSpec> = 
  T extends number ? [number] :
  T extends number[] ? T :
  T extends `${infer N}u${infer M}` ? Array<number> :
  [1];

type ParseFps<T extends FpsSpec> =
  T extends number ? T :
  T extends `${infer N}hz` ? number :
  T extends `${infer N}ms` ? 1000 / number :
  30;

// Usage with type inference
function createSacnSource<T extends FpsSpec>(fps: T): SacnSourceNode {
  const parsedFps = parseFps(fps); // Type is ParseFps<T>
  return new SacnSourceNode({ fps: parsedFps });
}
```

**Runtime Validation Helpers**:
```typescript
// Compile-time validation with runtime check
function validateType<T>(value: unknown, validator: (v: unknown) => v is T): T {
  if (!validator(value)) {
    throw new Error(`Invalid type: expected ${typeof value}`);
  }
  return value;
}

// Type predicates
const isNumber = (v: unknown): v is number => typeof v === "number";
const isString = (v: unknown): v is string => typeof v === "string";
const isNumberArray = (v: unknown): v is number[] => 
  Array.isArray(v) && v.every(isNumber);
```

### 2. Typed Payload System
**Generic Payload Interface**:
```typescript
interface TypedPayload<TDomain extends string, TShape> extends FramePayload {
  readonly domain: TDomain;
  readonly shape: TShape;
  data: Float32Array;
}

// Domain-specific payload types
type MatrixShape = { count: number; channels: number };
type ColorShape = { count: number; model: ColorModel };
type BoolShape = { count: number };

class MatrixPayload extends TypedPayload<"matrix", MatrixShape> {
  static readonly domain = "matrix" as const;
  
  constructor(data: Float32Array, public readonly channels: number) {
    super();
    this.data = data;
    this.shape = { count: data.length / channels, channels };
  }
  
  get count(): number {
    return this.shape.count;
  }
}

class ColorPayload extends TypedPayload<"color", ColorShape> {
  static readonly domain = "color" as const;
  
  constructor(
    data: Float32Array,
    public readonly model: ColorModel,
  ) {
    super();
    this.data = data;
    this.shape = { count: data.length / 3, model };
  }
}
```

**Type-Safe Port Specifications**:
```typescript
interface PortSpec<TDomain extends string, TShape> {
  domain: TDomain;
  shape?: TShape;
  accepts?: TDomain | TDomain[];
}

// Typed port groups
class TypedPortGroup<TDomain extends string> {
  private ports = new Map<string, Port<TDomain>>();
  
  input<TName extends string>(
    name: TName,
    spec: PortSpec<TDomain, any>
  ): InputPort<TDomain> {
    const port = new InputPort<TDomain>(name, spec);
    this.ports.set(name, port);
    return port;
  }
  
  // Compile-time port access
  get<TName extends string>(name: TName): Port<TDomain> | undefined {
    return this.ports.get(name);
  }
}
```

### 3. Branded Types for Units
**Brand Types**:
```typescript
// Create branded types
type Hz<T extends number> = T & { readonly __brand: "Hz" };
type Ms<T extends number> = T & { readonly __brand: "ms" };
type Seconds<T extends number> = T & { readonly __brand: "seconds" };
type Ratio<T extends number> = T & { readonly __brand: "ratio" };

// Type-safe constructors
const hz = <T extends number>(value: T): Hz<T> => value as Hz<T>;
const ms = <T extends number>(value: T): Ms<T> => value as Ms<T>;
const seconds = <T extends number>(value: T): Seconds<T> => value as Seconds<T>;
const ratio = <T extends number>(value: T): Ratio<T> => value as Ratio<T>;

// Type-safe conversions
const msToHz = (ms: Ms<number>): Hz<number> => hz(1000 / ms);
const hzToMs = (hz: Hz<number>): Ms<number> => ms(1000 / hz);

// Usage in interfaces
interface IWaveformConfig {
  frequency?: Hz<number>;
  phase?: Ratio<number>;  // 0-1
}

interface ISchedulerConfig {
  frameBudget?: Ms<number>;
  maxDuration?: Seconds<number>;
}

// Compile-time error prevention
function setFrequency(config: IWaveformConfig, freq: Hz<number>) {
  config.frequency = freq;  // OK
  // config.frequency = config.frameBudget;  // Compile error!
}
```

### 4. Typed Configuration System
**Schema-Based Types**:
```typescript
// Define configuration schema
interface LiteralConfigSchema {
  id: string;
  value: NumberArray | NestedNumberArray;
  model?: ColorModel;
}

// Generate types from schema
type LiteralConfig = ValidateSchema<LiteralConfigSchema>;

// Array type helpers
type NumberArray = readonly number[];
type NestedNumberArray = readonly (readonly number[])[];
type ColorModel = "rgb" | "hsl" | "oklch";

// Schema validator
class SchemaValidator<T> {
  constructor(private schema: SchemaShape<T>) {}
  
  validate(data: unknown): T {
    return this.validateValue(data, this.schema) as T;
  }
  
  private validateValue(value: unknown, schema: SchemaShape<any>): any {
    // Implementation would validate recursively
    if (schema.type === "string") {
      return typeof value === "string" ? value : this.error("string", value);
    }
    // ... other types
  }
}

// Usage
const literalValidator = new SchemaValidator<LiteralConfigSchema>({
  id: { type: "string", required: true },
  value: { type: "array", elementType: "number", required: true },
  model: { type: "enum", values: ["rgb", "hsl", "oklch"] },
});

// Type-safe constructor
class LiteralNode extends BaseNode {
  constructor(config: LiteralConfig) {
    // No runtime validation needed - already validated
    super({ id: config.id });
    this._value = config.value;
    this._model = config.model;
  }
}
```

### 5. Generic Node Interfaces
**Strongly-Typed Node Base**:
```typescript
interface INodeConfig<TMetadata extends Record<string, unknown> = {}> {
  readonly id: string;
  readonly metadata?: TMetadata;
}

interface INode<TConfig extends INodeConfig, TInputs extends Record<string, any>, TOutputs extends Record<string, any>> {
  readonly id: string;
  readonly config: TConfig;
  readonly inputs: TypedPortGroup<TInputs>;
  readonly outputs: TypedPortGroup<TOutputs>;
  
  start(context: NodeContext): Promise<void>;
  stop(context: NodeContext): Promise<void>;
  pull(tick: ITickContext): Promise<void>;
}

// Example node with strong typing
interface WaveformConfig extends INodeConfig<{
  version?: string;
}> {
  shape?: WaveShape;
  frequency?: Hz<number>;
  phase?: Ratio<number>;
}

interface WaveformInputs {
  phase?: "matrix";
  speed?: "matrix";
}

interface WaveformOutputs {
  out: "matrix";
}

class WaveformNode implements INode<WaveformConfig, WaveformInputs, WaveformOutputs> {
  public readonly inputs: TypedPortGroup<WaveformInputs>;
  public readonly outputs: TypedPortGroup<WaveformOutputs>;
  
  constructor(public readonly config: WaveformConfig) {
    this.id = config.id;
    // Typed port creation
    this.outputs = new TypedPortGroup<WaveformOutputs>()
      .output("out", { domain: "matrix" });
  }
  
  async pull(tick: ITickContext): Promise<void> {
    // Type-safe port access
    const outPort = this.outputs.get("out")!;  // No casting!
    // ... implementation
  }
}
```

## Implementation Plan

### Phase 1: Branded Types (High Priority)
1. Define branded types for common units
2. Create type-safe constructors and converters
3. Update configuration interfaces
4. Add unit conversion utilities

### Phase 2: Typed Payload System (High Priority)
1. Add generic TypedPayload interface
2. Update existing payload classes
3. Create typed port specifications
4. Update port group implementations

### Phase 3: Compile-Time Guards (Medium Priority)
1. Replace runtime checks with type guards
2. Create parser types for common formats
3. Update configuration parsing
4. Add validation helpers

### Phase 4: Generic Node System (Medium Priority)
1. Define strongly-typed node interfaces
2. Update base node class
3. Create typed port groups
4. Update node implementations

### Phase 5: Schema Validation (Low Priority)
1. Implement schema validator
2. Create configuration schemas
3. Add automatic type generation
4. Update documentation

## Success Criteria

- [ ] Unit mixing errors caught at compile time
- [ ] Payload domains are type-safe
- [ ] Configuration validation at type level
- [ ] No runtime type checks in hot paths
- [ ] Better IDE support and autocomplete
- [ ] Backward compatibility maintained

## Open Questions

1. How to handle dynamic configuration (e.g., from JSON files)?
2. Should branded types have runtime representation?
3. How to migrate existing code without breaking changes?
4. Should we use a type assertion library like Zod?
5. How to handle optional vs required configuration elegantly?
