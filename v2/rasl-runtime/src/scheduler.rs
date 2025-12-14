//! Tick-based pull scheduler for RASL graphs.
//!
//! The scheduler is the single time authority. It computes exact tick times
//! based on sink rates and executes the graph with minimal jitter.

use rasl_core::frame::Frame;
use rasl_core::graph::{Edge, ExecutionPlan};
use rasl_core::node::{Node, NodeContext, NodeId, NodeResult};
use rasl_core::payload::{MatrixPayload, Payload};
use rasl_core::tick::TickContext;
use std::collections::{HashMap, HashSet};
use std::time::{Duration, Instant};
use thiserror::Error;
use tokio::sync::mpsc;
use tokio::time::sleep;
use tracing::{debug, error, info, warn};

/// Errors during scheduler execution.
#[derive(Debug, Error)]
pub enum SchedulerError {
    #[error("No rate-driving sinks in graph")]
    NoRateDrivers,

    #[error("Node error: {0}")]
    NodeError(#[from] rasl_core::node::NodeError),

    #[error("Scheduler stopped")]
    Stopped,
}

/// Result type for scheduler operations.
pub type SchedulerResult<T> = Result<T, SchedulerError>;

/// A scheduled tick slot.
#[derive(Debug, Clone)]
struct TickSlot {
    /// Time offset from cycle start (seconds).
    time_offset: f64,

    /// Sink node IDs to pull at this slot.
    sinks: Vec<NodeId>,
}

/// Frame cache key.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct CacheKey {
    node_id: NodeId,
    port: String,
    tick: u64,
}

/// Tick-based pull scheduler.
///
/// The scheduler drives graph execution by:
/// 1. Finding rate-driving sinks (nodes with pull_rate)
/// 2. Computing tick schedule to hit all rates
/// 3. Pulling sinks at scheduled times
/// 4. Recursively pulling upstream nodes as needed
/// 5. Caching frames per-tick to avoid redundant computation
pub struct Scheduler {
    /// The execution plan.
    plan: ExecutionPlan,

    /// Tick schedule (1-second cycle).
    schedule: Vec<TickSlot>,

    /// Frame cache: (node_id, port, tick) -> Frame.
    frame_cache: HashMap<CacheKey, Frame<MatrixPayload>>,

    /// Current tick context.
    tick: TickContext,

    /// Start time.
    t0: Instant,

    /// Nodes currently being pulled (cycle detection).
    in_progress: HashSet<NodeId>,

    /// Shutdown flag.
    running: bool,
}

impl Scheduler {
    /// Create a new scheduler for the given execution plan.
    pub fn new(plan: ExecutionPlan) -> SchedulerResult<Self> {
        let schedule = Self::build_schedule(&plan.rate_drivers);

        if schedule.is_empty() && !plan.rate_drivers.is_empty() {
            return Err(SchedulerError::NoRateDrivers);
        }

        Ok(Self {
            plan,
            schedule,
            frame_cache: HashMap::new(),
            tick: TickContext::default(),
            t0: Instant::now(),
            in_progress: HashSet::new(),
            running: false,
        })
    }

    /// Build the tick schedule from rate drivers.
    fn build_schedule(rate_drivers: &HashMap<NodeId, f64>) -> Vec<TickSlot> {
        if rate_drivers.is_empty() {
            return Vec::new();
        }

        let duration = 1.0; // 1-second cycle
        let mut all_ticks: Vec<(f64, NodeId)> = Vec::new();

        for (sink_id, hz) in rate_drivers {
            let interval = 1.0 / hz;
            let mut t = 0.0;
            while t < duration - 1e-9 {
                all_ticks.push((t, sink_id.clone()));
                t += interval;
            }
        }

        all_ticks.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());

        // Merge ticks at same time
        let mut slots: Vec<TickSlot> = Vec::new();
        let epsilon = 1e-6;

        for (time_offset, sink_id) in all_ticks {
            if let Some(last) = slots.last_mut() {
                if (last.time_offset - time_offset).abs() < epsilon {
                    last.sinks.push(sink_id);
                    continue;
                }
            }
            slots.push(TickSlot {
                time_offset,
                sinks: vec![sink_id],
            });
        }

        info!(
            num_slots = slots.len(),
            rate_drivers = ?rate_drivers.keys().collect::<Vec<_>>(),
            "schedule_built"
        );

        slots
    }

    /// Start all nodes.
    pub fn start(&mut self) -> SchedulerResult<()> {
        info!("starting_scheduler");
        self.t0 = Instant::now();
        self.running = true;

        // Start nodes in topological order
        for node_id in &self.plan.topo_order.clone() {
            let ctx = NodeContext::new(node_id.clone());
            if let Some(node) = self.plan.nodes.get_mut(node_id) {
                node.start(&ctx)?;
            }
        }

        Ok(())
    }

    /// Stop all nodes.
    pub fn stop(&mut self) -> SchedulerResult<()> {
        info!("stopping_scheduler");
        self.running = false;

        // Stop nodes in reverse topological order
        for node_id in self.plan.topo_order.iter().rev() {
            let ctx = NodeContext::new(node_id.clone());
            if let Some(node) = self.plan.nodes.get_mut(node_id) {
                if let Err(e) = node.stop(&ctx) {
                    warn!(node_id = %node_id, error = %e, "node_stop_error");
                }
            }
        }

        Ok(())
    }

    /// Run the scheduler (blocking).
    pub async fn run(&mut self) -> SchedulerResult<()> {
        self.start()?;

        if self.schedule.is_empty() {
            info!("no_schedule_running_once");
            // Run once for graphs without rate drivers
            self.execute_tick()?;
            return Ok(());
        }

        let cycle_duration = Duration::from_secs(1);
        let mut cycle_start = Instant::now();
        let mut slot_index = 0;

        while self.running {
            let slot = &self.schedule[slot_index];
            let target_time = cycle_start + Duration::from_secs_f64(slot.time_offset);

            // Sleep until target time
            let now = Instant::now();
            if target_time > now {
                sleep(target_time - now).await;
            }

            // Execute tick for this slot's sinks
            self.execute_tick_for_sinks(&slot.sinks.clone())?;

            // Advance to next slot
            slot_index += 1;
            if slot_index >= self.schedule.len() {
                slot_index = 0;
                cycle_start += cycle_duration;
            }
        }

        self.stop()?;
        Ok(())
    }

    /// Run for a fixed number of ticks (for testing).
    /// Uses simulated time advancement based on the fastest rate driver.
    pub fn run_ticks(&mut self, count: u64) -> SchedulerResult<()> {
        self.start()?;

        // Calculate simulated dt based on fastest rate driver
        let max_rate = self.plan.rate_drivers.values()
            .cloned()
            .fold(1.0_f64, f64::max);
        let simulated_dt = 1.0 / max_rate;

        for i in 0..count {
            self.execute_tick_simulated(i, simulated_dt)?;
        }

        self.stop()?;
        Ok(())
    }

    /// Execute a single tick with simulated time.
    fn execute_tick_simulated(&mut self, tick_num: u64, dt: f64) -> SchedulerResult<()> {
        // Clear frame cache for new tick
        self.frame_cache.clear();

        // Use simulated time
        let t = tick_num as f64 * dt;
        self.tick = TickContext::new(self.tick.tick + 1, t, dt, t);

        // Pull all rate-driving sinks
        let sink_ids: Vec<NodeId> = self.plan.rate_drivers.keys().cloned().collect();
        for sink_id in &sink_ids {
            self.pull_node(sink_id)?;
        }

        Ok(())
    }

    /// Execute a single tick.
    fn execute_tick(&mut self) -> SchedulerResult<()> {
        // Clear frame cache for new tick
        self.frame_cache.clear();

        // Update tick context
        let wall_time = self.t0.elapsed().as_secs_f64();
        let dt = if self.tick.tick == 0 {
            0.0
        } else {
            wall_time - self.tick.wall_time
        };
        self.tick = TickContext::new(self.tick.tick + 1, wall_time, dt, wall_time);

        // Pull all rate-driving sinks
        let sink_ids: Vec<NodeId> = self.plan.rate_drivers.keys().cloned().collect();
        self.execute_tick_for_sinks(&sink_ids)
    }

    /// Execute tick for specific sinks.
    fn execute_tick_for_sinks(&mut self, sink_ids: &[NodeId]) -> SchedulerResult<()> {
        // Clear frame cache for new tick
        self.frame_cache.clear();

        // Update tick context
        let wall_time = self.t0.elapsed().as_secs_f64();
        let dt = if self.tick.tick == 0 {
            0.0
        } else {
            wall_time - self.tick.wall_time
        };
        self.tick = TickContext::new(self.tick.tick + 1, wall_time, dt, wall_time);

        // Pull each sink
        for sink_id in sink_ids {
            self.pull_node(sink_id)?;
        }

        Ok(())
    }

    /// Pull a node, recursively pulling upstream nodes first.
    fn pull_node(&mut self, node_id: &str) -> SchedulerResult<Option<Frame<MatrixPayload>>> {
        // Cycle detection
        if self.in_progress.contains(node_id) {
            debug!(node_id = %node_id, "cycle_detected_using_previous");
            return Ok(None);
        }

        // Check cache
        let cache_key = CacheKey {
            node_id: node_id.to_string(),
            port: "out".to_string(),
            tick: self.tick.tick,
        };
        if let Some(frame) = self.frame_cache.get(&cache_key) {
            return Ok(Some(frame.clone()));
        }

        self.in_progress.insert(node_id.to_string());

        // Pull upstream nodes first
        let incoming_edges = self.plan.edges_to(node_id).to_vec();
        for edge in &incoming_edges {
            if let Some(frame) = self.pull_node(&edge.source)? {
                // Apply repeat/repeat_until modifiers
                let modified_frame = apply_edge_modifiers(frame, &edge);
                
                // Set frame on target input port
                if let Some(node) = self.plan.nodes.get(node_id) {
                    if let Some(port) = node.inputs().get(&edge.target_port) {
                        port.set(modified_frame);
                    }
                }
            }
        }

        // Pull this node
        if let Some(node) = self.plan.nodes.get_mut(node_id) {
            node.pull(&self.tick)?;

            // Get output frame
            if let Some(port) = node.outputs().get("out") {
                if let Some(frame) = port.take() {
                    self.frame_cache.insert(cache_key, frame.clone());
                    self.in_progress.remove(node_id);
                    return Ok(Some(frame));
                }
            }

            // Check for 'color' output (ColorNode)
            if let Some(port) = node.outputs().get("color") {
                if let Some(frame) = port.take() {
                    self.frame_cache.insert(cache_key, frame.clone());
                    self.in_progress.remove(node_id);
                    return Ok(Some(frame));
                }
            }
        }

        self.in_progress.remove(node_id);
        Ok(None)
    }

    /// Request shutdown.
    pub fn shutdown(&mut self) {
        self.running = false;
    }

    /// Check if running.
    pub fn is_running(&self) -> bool {
        self.running
    }

    /// Get current tick.
    pub fn current_tick(&self) -> &TickContext {
        &self.tick
    }
}

/// Apply edge modifiers (repeat, repeat_until) to a frame.
fn apply_edge_modifiers(frame: Frame<MatrixPayload>, edge: &Edge) -> Frame<MatrixPayload> {
    let payload = &frame.payload;
    let (count, channels) = (payload.count(), payload.channels());
    
    // No modifiers - return as-is
    if edge.repeat.is_none() && edge.repeat_until.is_none() {
        return frame;
    }
    
    // Calculate target count
    let target_count = if let Some(repeat_until) = edge.repeat_until {
        repeat_until
    } else if let Some(repeat) = edge.repeat {
        count * repeat
    } else {
        return frame;
    };
    
    if target_count <= count {
        return frame;
    }
    
    // Repeat the data
    let repeats = (target_count + count - 1) / count;
    let repeated = payload.repeat(repeats);
    
    // Truncate to exact target count if needed
    let final_payload = if repeated.count() > target_count {
        repeated.truncate(target_count)
    } else {
        repeated
    };
    
    frame.with_payload(final_payload)
}

#[cfg(test)]
mod tests {
    use super::*;
    use rasl_core::graph::GraphBuilder;
    use rasl_core::port::{InputPorts, OutputPorts, OutputPort, PortSpec};

    struct TestSource {
        id: String,
        inputs: InputPorts,
        outputs: OutputPorts,
        value: f32,
    }

    impl TestSource {
        fn new(id: &str, value: f32) -> Self {
            let mut outputs = OutputPorts::new();
            outputs.add(OutputPort::new(PortSpec::new("out", "matrix")));
            Self {
                id: id.to_string(),
                inputs: InputPorts::new(),
                outputs,
                value,
            }
        }
    }

    impl Node for TestSource {
        rasl_core::impl_node_basics!(TestSource, id, inputs, outputs);

        fn pull(&mut self, tick: &TickContext) -> NodeResult<()> {
            let payload = MatrixPayload::from_slice(&[self.value]);
            let frame = Frame::with_timestamp(&self.id, tick.wall_time, payload);
            self.outputs.get("out").unwrap().write(frame);
            Ok(())
        }
    }

    struct TestSink {
        id: String,
        inputs: InputPorts,
        outputs: OutputPorts,
        fps: f64,
        received: Vec<f32>,
    }

    impl TestSink {
        fn new(id: &str, fps: f64) -> Self {
            use rasl_core::port::InputPort;
            let mut inputs = InputPorts::new();
            inputs.add(InputPort::new(PortSpec::new("in", "matrix")));
            Self {
                id: id.to_string(),
                inputs,
                outputs: OutputPorts::new(),
                fps,
                received: Vec::new(),
            }
        }
    }

    impl Node for TestSink {
        rasl_core::impl_node_basics!(TestSink, id, inputs, outputs);

        fn pull(&mut self, _tick: &TickContext) -> NodeResult<()> {
            if let Some(frame) = self.inputs.get("in").and_then(|p| p.read()) {
                if let Some(row) = frame.payload.row(0) {
                    self.received.push(row[0]);
                }
            }
            Ok(())
        }

        fn pull_rate(&self) -> Option<f64> {
            Some(self.fps)
        }
    }

    #[test]
    fn test_scheduler_build_schedule() {
        let mut drivers = HashMap::new();
        drivers.insert("sink1".to_string(), 30.0);
        drivers.insert("sink2".to_string(), 60.0);

        let schedule = Scheduler::build_schedule(&drivers);
        assert!(!schedule.is_empty());
    }

    #[test]
    fn test_scheduler_run_ticks() {
        let mut builder = GraphBuilder::new();
        builder.add_node(Box::new(TestSource::new("source", 42.0))).unwrap();
        builder.add_node(Box::new(TestSink::new("sink", 30.0))).unwrap();
        builder.connect("source", "out", "sink", "in").unwrap();

        let plan = builder.build().unwrap();
        let mut scheduler = Scheduler::new(plan).unwrap();

        scheduler.run_ticks(5).unwrap();
    }
}
