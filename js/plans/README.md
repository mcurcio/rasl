# RASL TypeScript Structural Improvements

This directory contains planning documents for addressing structural issues in the RASL TypeScript codebase. Each document focuses on a specific category of problems and proposes concrete solutions.

## Documents

### [domain-leakage.md](./domain-leakage.md)
**Domain Leakage & Boundary Violations**
- RASL-specific concepts bleeding into domain-agnostic packages
- Weak typing in logger API
- Mixed domain concerns in frame/payload system
- **Priority**: High
- **Impact**: Reusability, maintainability

### [performance-optimization.md](./performance-optimization.md)
**Performance Optimization & Drains**
- Excessive `any` casting bypassing TypeScript
- Dynamic prototype inspection in scheduler
- Unnecessary object creation
- Inefficient scheduler loop structure
- **Priority**: High
- **Impact**: Runtime performance, memory usage

### [api-ergonomics.md](./api-ergonomics.md)
**API Ergonomics & Complexity**
- Overloaded logger API with confusing semantics
- Inconsistent node configuration patterns
- Required port casting everywhere
- Verbose frame creation
- **Priority**: High
- **Impact**: Developer experience, code quality

### [missing-abstractions.md](./missing-abstractions.md)
**Missing Abstractions & Plugin System**
- No plugin system for node registration
- Weak error boundaries (no circuit breakers)
- Scattered metrics collection
- Missing event system
- **Priority**: Medium
- **Impact**: Extensibility, resilience

### [type-system-weaknesses.md](./type-system-weaknesses.md)
**Type System Weaknesses & Improvements**
- Runtime type checking instead of compile-time guards
- Weak payload type system
- Missing branded types for units
- Loose configuration types
- **Priority**: Medium
- **Impact**: Type safety, compile-time guarantees

## Implementation Priority

### Phase 1 (High Priority - Immediate)
1. **Logger API Redesign** - Foundation for all other improvements
2. **Remove `any` Casting** - Enable TypeScript optimizations
3. **Typed Port Access** - Eliminate casting throughout codebase
4. **Plugin System** - Enable extensibility

### Phase 2 (Medium Priority - Next)
1. **Domain Leakage Cleanup** - Improve package boundaries
2. **Typed Payload System** - Better type safety
3. **Circuit Breakers** - Improve resilience
4. **Unified Metrics** - Centralized observability

### Phase 3 (Lower Priority - Future)
1. **Branded Types** - Unit safety
2. **Object Pooling** - Performance optimization
3. **Event System** - Loose coupling
4. **Schema Validation** - Configuration safety

## Success Metrics

Each plan document defines specific success criteria. Overall goals:

- **Zero `any` casts** in production code
- **Compile-time type safety** for all domain boundaries
- **Plugin-based architecture** for extensibility
- **Unified observability** across all components
- **Performance targets** met (60+ FPS, low memory usage)

## Getting Started

1. Review each document to understand the problems
2. Start with Phase 1 high-priority items
3. Create implementation branches for each major change
4. Update this README as items are completed

## Notes

- All documents include implementation plans with specific phases
- Backward compatibility is considered where possible
- Test coverage is required for all changes
- Performance benchmarks should be established before optimization
