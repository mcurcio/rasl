# Questions & Assumptions Log

This log tracks decisions made during the Python → TypeScript migration per `js/plans/migrate.md` §8.

---

## 2024-01-04: Slice 1 - HTTP Server Core

### Assumptions Made

1. **No external HTTP framework**: Using Node's built-in `http` module rather than Express/Fastify/Hono.
   - *Rationale*: Keeps dependencies minimal; aligns with §4.1 (browser+Node packaging). The server package is Node-only anyway, but avoiding framework lock-in.

2. **REST over GraphQL**: Python uses Strawberry GraphQL, but TS implementation uses REST endpoints.
   - *Rationale*: GraphQL adds significant dependency weight. REST endpoints (`/health`, `/graph`, `/stats`, `/node/:id`) provide equivalent functionality with simpler implementation. Can add GraphQL later if needed.

3. **JSON API responses**: All endpoints return `application/json`.
   - *Rationale*: Standard practice; matches the Python GraphQL response format.

4. **CORS permissive by default**: `corsOrigins: ['*']` allows all origins.
   - *Rationale*: Matches existing `IServerConfig` defaults. Production deployments can restrict.

### Potential Behavior Risks

- Python GraphQL subscriptions use `graphql-transport-ws` protocol. TS WebSocket implementation (Slice 2) will need to decide on protocol.

### Follow-ups / TODOs

- [ ] WebSocket support for real-time metrics streaming
- [ ] Consider GraphQL if REST proves insufficient

---

## 2024-01-04: Slice 2 - Engine Unit Tests

### Summary

Added 34 unit tests for `@rasl/engine` runtime primitives:
- `Frame` (5 tests): construction, `withPayload()`, `withMetadata()`
- `MatrixPayload` (12 tests): construction, `get()`, `getRow()`, `repeat()`, `describe()`, `isCompatibleWith()`
- `BoolPayload` (4 tests): normalization of boolean/number/Float32Array inputs
- `GraphBuilder` (13 tests): `addNode()`, `connect()`, `connectDefault()`, `build()`, cycle handling, `describe()`

### Assumptions Made

1. **PortGroup factory pattern**: Used `PortGroup.inputs()` and `PortGroup.outputs()` static methods (private constructor).
   - *Rationale*: Follows existing codebase pattern; ensures type safety for input vs output ports.

2. **Cycle warning is acceptable**: Graph cycles emit a warning but don't throw.
   - *Rationale*: Matches Python behavior; allows feedback loops in signal processing graphs.

### Follow-ups / TODOs

- [ ] Add tests for `UnifiedScheduler` execution
- [x] Add color conversion stability tests per §5.3

---

## 2024-01-04: Slice 3 - Missing Nodes & WebSocket

### Summary

Implemented missing transform/source nodes and WebSocket support:

**New Transform Nodes:**
- `RangeMapNode` - Remaps channels from source range to [0,1]
- `SmoothNode` - Exponential smoothing with slew limiting
- `RandomMapNode` - Random channel mapping with seeded RNG
- `MatrixMultiplyNode` - Fixed matrix multiplication

**New Source Nodes:**
- `LiteralNode` - Constant value source

**WebSocket Support:**
- `WsHandler` class for real-time metrics streaming
- Subscribe/unsubscribe protocol for `metrics` topic
- Configurable broadcast interval

**Tests Added:**
- 6 tests for `RangeMapNode`
- 6 tests for `LiteralNode`
- 17 tests for color conversion (including §5.3 stability tests)

### Assumptions Made

1. **WebSocket protocol**: Simple JSON messages with `type`, `topic`, `payload` structure.
   - *Rationale*: Matches existing `IWsMessage` interface; simpler than GraphQL subscriptions.

2. **Metrics broadcast interval**: Minimum 50ms, default 1000ms.
   - *Rationale*: Prevents excessive CPU usage while allowing real-time monitoring.

3. **Node decorators**: All new nodes use `@node('TypeName', 'Alias')` decorator.
   - *Rationale*: Matches existing pattern for registry registration.

### Test Results

```text
Total: 147 tests passing
- @rasl/config: 72 tests
- @rasl/engine: 46 tests
- @rasl/color: 17 tests
- @rasl/server: 12 tests
```

### Deferred Items

1. **GoveeLightNode**: Govee LAN TCP protocol sink - requires custom client implementation.
2. **LifxSinkNode**: LIFX LAN protocol sink - requires custom client implementation.

*Rationale*: These are hardware-specific integrations that require external protocol clients. The core RASL functionality (graph execution, color processing, E1.31/DDP protocols) is complete. Govee/LIFX can be added later as needed.

---

## 2024-01-04: Slice 4 - Config Parity & Validation

### Summary

Added `#` comment support to the config lexer and validated the TypeScript server against `virtual.conf`.

### Changes

1. **# comment syntax**: Added support for Python/nginx-style `#` line comments in addition to `//`.
   - Modified `@/js/packages/config/src/lexer.ts` to recognize `#` as comment prefix.
   - Added test case for `#` comments.

### Validation

Successfully ran `virtual.conf` with the TypeScript server:

```bash
node dist/cli.js /Users/matt/Code/rasl/virtual.conf
```

Output shows:
- 512 channels of RGB color data
- Sawtooth-driven rainbow cycling through OkHSL → RGB conversion
- 1 FPS console output as configured
- Colors cycling: `#00ff80` → `#1aff80` → `#33ff80` → ... (green → yellow progression)

### Migration Complete ✅

The TypeScript implementation is now functionally equivalent to the Python reference for:

| Feature | Status |
|---------|--------|
| Config parsing (`.conf` files) | ✅ |
| Graph building & execution | ✅ |
| Source nodes (Waveform, SeededRandom, Literal) | ✅ |
| Transform nodes (Math, RangeMap, Smooth, RandomMap, MatrixMultiply) | ✅ |
| Color nodes (Color, Compose, Correction) | ✅ |
| Effect nodes (Crossfade, Twinkle, Cron) | ✅ |
| Sink nodes (Console, DDP, sACN/E1.31) | ✅ |
| Color conversion (sRGB, HSL, Oklab, Oklch, OkHSL, OkHSV) | ✅ |
| HTTP server with REST API | ✅ |
| WebSocket metrics streaming | ✅ |

### Deferred (Hardware-specific)

- GoveeLightNode
- LifxSinkNode

---
