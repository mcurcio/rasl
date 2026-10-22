# Domain Leakage & Boundary Violations

## Problem Statement

The TypeScript codebase has significant domain leakage where RASL-specific concepts bleed into supposedly domain-agnostic packages, creating tight coupling and making components difficult to reuse.

## Current Issues

### 1. @rasl/config RASL Leakage
**Location**: `packages/config/`

**Problem**: 
- Package describes itself as "domain-agnostic" but README mentions RASL
- Tests and JSDoc contain RASL-specific terminology
- Parser includes node-graph semantics that should be separate

**Impact**: 
- Cannot reuse config parser for other nginx-style config languages
- Confusing API surface mixing generic and specific concerns
- Hard to maintain clear boundaries

### 2. Logger API Weak Typing
**Location**: `packages/engine/src/log/index.ts`

**Problem**:
```typescript
interface ILogger {
  trace(a0: unknown, ...args: unknown[]): void;
  debug(a0: unknown, ...args: unknown[]): void;
  // ... all methods use unknown
}
```

**Impact**:
- No compile-time guarantees about log structure
- Runtime type checking everywhere
- Poor IDE support and refactoring safety

### 3. Frame/Payload Domain Mixing
**Location**: `packages/engine/src/runtime/`

**Problem**:
- Base `FramePayload` class has no domain specificity
- Domain concepts (color, matrix, bool) mixed with base abstractions
- `IPayloadDescriptor.domain` string-based instead of typed

**Impact**:
- Weak type safety between payload domains
- Difficult to add new payload types safely
- Runtime validation instead of compile-time guarantees

## Proposed Solutions

### 1. Extract RASL Graph Config
**New Package**: `@rasl/graph-config`

**Approach**:
- Move RASL-specific node graph building from `@rasl/config`
- Keep `@rasl/config` purely as nginx-style parser
- Create clean dependency: `@rasl/graph-config` → `@rasl/config`

**Files to Move**:
- `src/config/rasl.ts` → `@rasl/graph-config/src/rasl.ts`
- RASL-specific tests → `@rasl/graph-config/tests/`

### 2. Strongly-Typed Logger
**New Interface**:
```typescript
interface LogFields {
  nodeId?: string;
  tick?: number;
  elapsedMs?: number;
  // ... other known fields
}

interface ILogger {
  trace(fields: LogFields, message?: string): void;
  debug(fields: LogFields, message?: string): void;
  info(fields: LogFields, message?: string): void;
  warn(fields: LogFields, message?: string): void;
  error(fields: LogFields & { err: Error }, message?: string): void;
}
```

**Benefits**:
- Compile-time field validation
- Better IDE support
- Structured logging by default

### 3. Typed Payload System
**New Generic Interface**:
```typescript
interface TypedPayload<T extends PayloadDomain> extends FramePayload {
  readonly domain: T;
}

type PayloadDomain = "matrix" | "color" | "bool" | "audio" | "control";

// Domain-specific payloads
class MatrixPayload extends TypedPayload<"matrix"> { }
class ColorPayload extends TypedPayload<"color"> { }
```

**Benefits**:
- Compile-time domain safety
- Clear payload type boundaries
- Easier to add new domains

## Implementation Plan

### Phase 1: Logger API (High Priority)
1. Create new `ILogFields` interface with known fields
2. Update all logger implementations
3. Migrate all call sites to structured logging
4. Remove `unknown` overloads

### Phase 2: Config Extraction (Medium Priority)
1. Create `@rasl/graph-config` package
2. Move RASL-specific code from `@rasl/config`
3. Update dependencies in `@rasl/engine`
4. Update documentation and READMEs

### Phase 3: Typed Payloads (Medium Priority)
1. Add `TypedPayload<T>` generic interface
2. Update existing payloads to extend it
3. Add compile-time domain checks where needed
4. Update port specifications to use typed domains

## Success Criteria

- [ ] `@rasl/config` README mentions no RASL concepts
- [ ] All logger calls use typed fields, no `unknown`
- [ ] Payload types are compile-time domain-safe
- [ ] No regressions in existing functionality
- [ ] All tests pass with new APIs

## Open Questions

1. Should we support both old and new logger APIs during migration?
2. How to handle dynamic log fields that aren't known in advance?
3. Should typed payloads be backward compatible with existing code?
