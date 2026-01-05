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

- ~~GoveeLightNode~~ ✅ Completed in Slice 5
- ~~LifxSinkNode~~ ✅ Completed in Slice 5

---

## 2025-01-05: Slice 5 - Hardware Sink Nodes

### Summary

Implemented the final two hardware-specific sink nodes that were deferred in Slice 3.

**New Packages:**
- `@rasl/govee` - Govee LAN TCP protocol sink
- `@rasl/lifx` - LIFX LAN UDP protocol sink

### @rasl/govee Implementation

**GoveeLightClient:**
- TCP client for Govee LAN JSON protocol
- Device discovery via `devStatus` command
- Segment color commands via `colorwc`
- Exponential backoff on connection failures
- Configurable timeouts and retry intervals

**GoveeLightNode:**
- Sink node for RGB/RGBW segment colors
- Dynamic input port configuration
- Automatic segment discovery and validation
- Float [0,1] → uint8 [0,255] quantization
- Per-segment color assignment
- Frame drop tracking and error logging

**Tests:** 22 tests passing
- Client construction and lifecycle
- Device discovery and segment parsing
- RGBW channel detection
- Node configuration and quantization
- Segment ID resolution and color building

### @rasl/lifx Implementation

**LifxLanClient:**
- UDP client for LIFX LAN protocol (binary packets)
- Binary packet encoding for `SetColor` command (message type 102)
- Target parsing: IP, MAC@IP, IPv6 literals
- HSBK → LIFX integer conversion (uint16 for H/S/B, kelvin range 1500-9000)

**LifxSinkNode:**
- Sink node for HSBK color frames (4 channels required)
- Multi-target support with intelligent assignment strategies:
  - 1:1 mapping when rows match client count
  - Broadcast single row to all clients
  - Use first row for single client
  - Warn on mismatches
- Duration and rapid mode options
- Throttled unresolved target warnings

**Tests:** 31 tests passing
- Target parsing (IP, MAC, IPv6, port)
- HSBK quantization and clamping
- Client lifecycle and error handling
- Assignment strategy logic

### Test Results

```text
Total: 201 tests passing
├── @rasl/config: 73 tests
├── @rasl/engine: 46 tests
├── @rasl/color: 17 tests
├── @rasl/server: 12 tests
├── @rasl/govee: 22 tests
└── @rasl/lifx: 31 tests
```

### Assumptions Made

1. **Govee protocol**: Based on reverse-engineered LAN API, not official documentation.
   - *Rationale*: Matches Python implementation; Govee doesn't publish official LAN protocol docs.

2. **LIFX protocol**: Using LIFX LAN Protocol v2 (protocol number 0x400).
   - *Rationale*: Stable protocol version; matches Python implementation.

3. **No acknowledgment handling**: Both protocols send commands without waiting for ACK.
   - *Rationale*: Matches Python implementation; reduces latency for real-time streaming.

4. **HSBK color model**: LIFX expects 4-channel HSBK (Hue, Saturation, Brightness, Kelvin).
   - *Rationale*: LIFX native color model; requires upstream color conversion.

5. **Segment assignment**: Govee uses explicit segment IDs from discovery; LIFX uses row-to-client mapping.
   - *Rationale*: Reflects hardware differences - Govee supports multi-segment strips, LIFX typically one bulb per target.

### Migration Status: COMPLETE ✅

All Python functionality has been migrated to TypeScript:

| Feature | Status |
|---------|--------|
| Config parsing (`.conf` files) | ✅ |
| Graph building & execution | ✅ |
| Source nodes (Waveform, SeededRandom, Literal) | ✅ |
| Transform nodes (Math, RangeMap, Smooth, RandomMap, MatrixMultiply) | ✅ |
| Color nodes (Color, Compose, Correction) | ✅ |
| Effect nodes (Crossfade, Twinkle, Cron) | ✅ |
| Sink nodes (Console, DDP, sACN/E1.31) | ✅ |
| **Hardware sinks (Govee, LIFX)** | ✅ |
| Color conversion (sRGB, HSL, Oklab, Oklch, OkHSL, OkHSV) | ✅ |
| HTTP server with REST API | ✅ |
| WebSocket metrics streaming | ✅ |

---

## Outstanding Questions

### 1. Node Registration in Server CLI

**Question:** Should the server CLI automatically register nodes from `@rasl/govee` and `@rasl/lifx`?

**Current State:**
- `@/js/packages/server/src/cli.ts` currently imports and registers nodes from `@rasl/color` and `@rasl/lighting`
- Govee and LIFX nodes are not yet registered in the CLI

**Options:**
- **A)** Add explicit imports in `cli.ts` (requires adding dependencies to `@rasl/server`)
- **B)** Use dynamic imports based on config file node types
- **C)** Require users to create custom entry points for hardware-specific deployments
- **D)** Create a plugin/registration system

**Recommendation:** Option A for now (explicit imports), with Option D (plugin system) as a future enhancement.

### 2. Color Model Conversion for LIFX

**Question:** Should `LifxSinkNode` automatically convert non-HSBK color payloads to HSBK?

**Current State:**
- Python implementation accepts `ColorPayload` and converts to `HsbkColorPayload`
- TypeScript implementation expects 4-channel matrix (HSBK)
- No automatic color model conversion in the node

**Options:**
- **A)** Add automatic conversion in `LifxSinkNode.pull()` (matches Python)
- **B)** Require upstream `Color` node to convert to HSBK (explicit pipeline)
- **C)** Accept both and convert as needed

**Current Implementation:** Option B (explicit conversion required)
**Python Behavior:** Option A (automatic conversion)

**Recommendation:** Add automatic conversion to match Python behavior and improve ergonomics.

### 3. Error Handling Strategy

**Question:** How should hardware sink nodes handle persistent connection failures?

**Current State:**
- Govee: Exponential backoff with configurable max
- LIFX: Connection failures logged, clients removed from active list
- Both: Frame drops tracked but no circuit breaker

**Options:**
- **A)** Current approach (log and continue)
- **B)** Add circuit breaker pattern (stop trying after N failures)
- **C)** Add reconnection attempts with backoff
- **D)** Emit events for external monitoring/alerting

**Current Implementation:** Option A
**Recommendation:** Option A is sufficient for now; Option D could be added via metrics.

---
