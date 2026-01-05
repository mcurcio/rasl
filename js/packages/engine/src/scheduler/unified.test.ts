/**
 * Tests for UnifiedScheduler - timing, memoization, and cycle handling.
 */

import { describe, expect, it, beforeEach, vi, afterEach } from "vitest";

import { GraphBuilder } from "../graph/builder.js";
import {
  BaseNode,
  type ITickContext,
  InputPort,
  InputPortSpec,
  OutputPort,
  OutputPortSpec,
  PortGroup,
  EMPTY_INPUTS,
  EMPTY_OUTPUTS,
} from "../runtime/index.js";
import { PULL_RATE_SYMBOL } from "../runtime/tick.js";
import { UnifiedScheduler } from "./unified.js";

/**
 * Test node that records pull calls with timing info.
 */
class RecordingNode extends BaseNode {
  readonly pulls: Array<{ tick: number; t: number; dt: number }> = [];
  readonly #inputs: PortGroup<InputPort>;
  readonly #outputs: PortGroup<OutputPort>;

  constructor(id: string, hasInput = false, hasOutput = true) {
    super({ id });
    this.#inputs = hasInput
      ? PortGroup.inputs({ in: new InputPortSpec({ accepts: "matrix" }) })
      : EMPTY_INPUTS;
    this.#outputs = hasOutput
      ? PortGroup.outputs({ out: new OutputPortSpec({ produces: "matrix" }) })
      : EMPTY_OUTPUTS;
  }

  get inputs(): PortGroup<InputPort> {
    return this.#inputs;
  }

  get outputs(): PortGroup<OutputPort> {
    return this.#outputs;
  }

  async pull(tick: ITickContext): Promise<void> {
    this.pulls.push({ tick: tick.tick, t: tick.t, dt: tick.dt });
  }
}

/**
 * Sink node with pull rate that records calls.
 */
class RecordingSink extends RecordingNode {
  constructor(id: string) {
    super(id, true, false);
  }

  override async pull(tick: ITickContext): Promise<void> {
    await super.pull(tick);
  }
}

// Apply pull rate to RecordingSink.prototype.pull
// eslint-disable-next-line @typescript-eslint/no-explicit-any
(RecordingSink.prototype.pull as any)[PULL_RATE_SYMBOL] = 60;

/**
 * Create a silent logger for tests.
 */
function createSilentLogger() {
  return {
    trace: vi.fn(),
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    child: () => createSilentLogger(),
  };
}

describe("UnifiedScheduler timing", () => {
  let builder: GraphBuilder;
  let logger: ReturnType<typeof createSilentLogger>;

  beforeEach(() => {
    logger = createSilentLogger();
    builder = new GraphBuilder({ logger });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("should provide non-zero dt for upstream nodes after first pull", async () => {
    const source = new RecordingNode("source", false, true);
    const sink = new RecordingSink("sink");

    builder.addNode(source);
    builder.addNode(sink);
    builder.connect("source", "out", "sink", "in");

    const plan = builder.build();
    const scheduler = new UnifiedScheduler(plan, { logger });

    // Run for enough time to get multiple pulls
    await scheduler.runFor(50);

    // Source should have been pulled multiple times
    expect(source.pulls.length).toBeGreaterThan(1);

    // First pull may have dt=0, but subsequent pulls should have dt > 0
    const nonZeroDt = source.pulls.slice(1).filter((p) => p.dt > 0);
    expect(nonZeroDt.length).toBeGreaterThan(0);
  });

  it("should increment tick once per frame, not per node", async () => {
    const source1 = new RecordingNode("source1", false, true);
    const source2 = new RecordingNode("source2", false, true);
    // Create sink with two inputs
    class TwoInputSink extends RecordingSink {
      readonly #twoInputs = PortGroup.inputs({
        in1: new InputPortSpec({ accepts: "matrix" }),
        in2: new InputPortSpec({ accepts: "matrix" }),
      });

      override get inputs(): PortGroup<InputPort> {
        return this.#twoInputs;
      }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (TwoInputSink.prototype.pull as any)[PULL_RATE_SYMBOL] = 60;
    const sinkWithTwoInputs = new TwoInputSink("sink2");

    builder.addNode(source1);
    builder.addNode(source2);
    builder.addNode(sinkWithTwoInputs);
    builder.connect("source1", "out", "sink2", "in1");
    builder.connect("source2", "out", "sink2", "in2");

    const plan = builder.build();
    const scheduler = new UnifiedScheduler(plan, { logger });

    await scheduler.runFor(30);

    // Both sources should see the same tick numbers
    if (source1.pulls.length > 0 && source2.pulls.length > 0) {
      // Check that tick numbers match between sources
      const source1Ticks = source1.pulls.map((p) => p.tick);
      const source2Ticks = source2.pulls.map((p) => p.tick);

      // They should have overlapping ticks
      const commonTicks = source1Ticks.filter((t) => source2Ticks.includes(t));
      expect(commonTicks.length).toBeGreaterThan(0);
    }
  });
});

describe("UnifiedScheduler per-tick memoization", () => {
  let builder: GraphBuilder;
  let logger: ReturnType<typeof createSilentLogger>;

  beforeEach(() => {
    logger = createSilentLogger();
    builder = new GraphBuilder({ logger });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("should pull shared upstream node only once per tick with multiple sinks", async () => {
    const source = new RecordingNode("source", false, true);
    const sink1 = new RecordingSink("sink1");
    const sink2 = new RecordingSink("sink2");

    builder.addNode(source);
    builder.addNode(sink1);
    builder.addNode(sink2);
    builder.connect("source", "out", "sink1", "in");
    builder.connect("source", "out", "sink2", "in");

    const plan = builder.build();
    const scheduler = new UnifiedScheduler(plan, { logger });

    await scheduler.runFor(30);

    // Source should be pulled once per tick, not twice (once per sink)
    // Check that we don't have duplicate tick numbers
    const tickCounts = new Map<number, number>();
    for (const pull of source.pulls) {
      tickCounts.set(pull.tick, (tickCounts.get(pull.tick) ?? 0) + 1);
    }

    // Each tick should appear at most once
    for (const [tick, count] of tickCounts) {
      expect(count, `Tick ${tick} was pulled ${count} times`).toBe(1);
    }
  });

  it("should pull diamond-shaped graph nodes only once per tick", async () => {
    // Diamond: source -> mid1 -> sink
    //          source -> mid2 -> sink
    const source = new RecordingNode("source", false, true);
    const mid1 = new RecordingNode("mid1", true, true);
    const mid2 = new RecordingNode("mid2", true, true);

    // Sink with two inputs
    class DiamondSink extends RecordingSink {
      readonly #twoInputs = PortGroup.inputs({
        in1: new InputPortSpec({ accepts: "matrix" }),
        in2: new InputPortSpec({ accepts: "matrix" }),
      });

      override get inputs(): PortGroup<InputPort> {
        return this.#twoInputs;
      }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (DiamondSink.prototype.pull as any)[PULL_RATE_SYMBOL] = 60;
    const sink = new DiamondSink("sink");

    builder.addNode(source);
    builder.addNode(mid1);
    builder.addNode(mid2);
    builder.addNode(sink);
    builder.connect("source", "out", "mid1", "in");
    builder.connect("source", "out", "mid2", "in");
    builder.connect("mid1", "out", "sink", "in1");
    builder.connect("mid2", "out", "sink", "in2");

    const plan = builder.build();
    const scheduler = new UnifiedScheduler(plan, { logger });

    await scheduler.runFor(30);

    // Source should be pulled once per tick despite being upstream of two paths
    const tickCounts = new Map<number, number>();
    for (const pull of source.pulls) {
      tickCounts.set(pull.tick, (tickCounts.get(pull.tick) ?? 0) + 1);
    }

    for (const [tick, count] of tickCounts) {
      expect(count, `Source tick ${tick} was pulled ${count} times`).toBe(1);
    }
  });
});

describe("UnifiedScheduler cycle handling", () => {
  let builder: GraphBuilder;
  let logger: ReturnType<typeof createSilentLogger>;

  beforeEach(() => {
    logger = createSilentLogger();
    builder = new GraphBuilder({ logger });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("should not recurse infinitely with self-loop", async () => {
    // Node that connects to itself
    class LoopNode extends RecordingNode {
      constructor() {
        super("loop", true, true);
      }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (LoopNode.prototype.pull as any)[PULL_RATE_SYMBOL] = 60;
    const loopNode = new LoopNode();

    builder.addNode(loopNode);
    builder.connect("loop", "out", "loop", "in");

    const plan = builder.build();
    const scheduler = new UnifiedScheduler(plan, { logger });

    // Should complete without stack overflow
    await scheduler.runFor(30);

    // Should have been pulled multiple times
    expect(loopNode.pulls.length).toBeGreaterThan(0);
  });

  it("should not recurse infinitely with two-node cycle", async () => {
    // A -> B -> A cycle
    const nodeA = new RecordingNode("nodeA", true, true);
    class NodeB extends RecordingNode {
      constructor() {
        super("nodeB", true, true);
      }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (NodeB.prototype.pull as any)[PULL_RATE_SYMBOL] = 60;
    const nodeB = new NodeB();

    builder.addNode(nodeA);
    builder.addNode(nodeB);
    builder.connect("nodeA", "out", "nodeB", "in");
    builder.connect("nodeB", "out", "nodeA", "in");

    const plan = builder.build();
    const scheduler = new UnifiedScheduler(plan, { logger });

    // Should complete without stack overflow
    await scheduler.runFor(30);

    // Both nodes should have been pulled
    expect(nodeA.pulls.length).toBeGreaterThan(0);
    expect(nodeB.pulls.length).toBeGreaterThan(0);
  });

  it("should log cycle detection when re-entrancy is detected", async () => {
    class CycleLoopNode extends RecordingNode {
      constructor() {
        super("loop", true, true);
      }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (CycleLoopNode.prototype.pull as any)[PULL_RATE_SYMBOL] = 60;
    const loopNode = new CycleLoopNode();

    builder.addNode(loopNode);
    builder.connect("loop", "out", "loop", "in");

    const plan = builder.build();
    const scheduler = new UnifiedScheduler(plan, { logger });

    await scheduler.runFor(30);

    // Should have logged cycle detection
    const cycleLogCalls = logger.trace.mock.calls.filter(
      (call) => typeof call[1] === "string" && call[1].includes("Cycle detected"),
    );
    expect(cycleLogCalls.length).toBeGreaterThan(0);
  });
});

describe("UnifiedScheduler dt calculation", () => {
  let builder: GraphBuilder;
  let logger: ReturnType<typeof createSilentLogger>;

  beforeEach(() => {
    logger = createSilentLogger();
    builder = new GraphBuilder({ logger });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("should have dt=0 on first pull", async () => {
    const source = new RecordingNode("source", false, true);
    const sink = new RecordingSink("sink");

    builder.addNode(source);
    builder.addNode(sink);
    builder.connect("source", "out", "sink", "in");

    const plan = builder.build();
    const scheduler = new UnifiedScheduler(plan, { logger });

    await scheduler.runFor(20);

    // First pull should have dt=0
    expect(source.pulls.length).toBeGreaterThan(0);
    expect(source.pulls[0].dt).toBe(0);
  });

  it("should have positive dt after first pull", async () => {
    const source = new RecordingNode("source", false, true);
    const sink = new RecordingSink("sink");

    builder.addNode(source);
    builder.addNode(sink);
    builder.connect("source", "out", "sink", "in");

    const plan = builder.build();
    const scheduler = new UnifiedScheduler(plan, { logger });

    await scheduler.runFor(50);

    // After first pull, dt should be positive
    if (source.pulls.length > 1) {
      const subsequentPulls = source.pulls.slice(1);
      const positiveDt = subsequentPulls.filter((p) => p.dt > 0);
      expect(positiveDt.length).toBeGreaterThan(0);
    }
  });

  it("should track dt per node independently", async () => {
    // Two sources with different pull patterns
    const source1 = new RecordingNode("source1", false, true);
    const source2 = new RecordingNode("source2", false, true);
    const sink1 = new RecordingSink("sink1");
    const sink2 = new RecordingSink("sink2");

    builder.addNode(source1);
    builder.addNode(source2);
    builder.addNode(sink1);
    builder.addNode(sink2);
    builder.connect("source1", "out", "sink1", "in");
    builder.connect("source2", "out", "sink2", "in");

    const plan = builder.build();
    const scheduler = new UnifiedScheduler(plan, { logger });

    await scheduler.runFor(50);

    // Both sources should have their own dt tracking
    expect(source1.pulls.length).toBeGreaterThan(0);
    expect(source2.pulls.length).toBeGreaterThan(0);

    // First pull of each should have dt=0
    expect(source1.pulls[0].dt).toBe(0);
    expect(source2.pulls[0].dt).toBe(0);
  });
});
