//! Node trait and context for graph processing.
//!
//! Nodes are the fundamental processing units in the RASL graph.
//! They read from input ports, process data, and write to output ports.

use crate::port::{InputPorts, OutputPorts};
use crate::tick::TickContext;
use std::any::Any;
use std::fmt;
use thiserror::Error;

/// Unique identifier for a node in the graph.
pub type NodeId = String;

/// Errors that can occur during node execution.
#[derive(Debug, Error)]
pub enum NodeError {
    #[error("Node '{0}' failed to start: {1}")]
    StartFailed(NodeId, String),

    #[error("Node '{0}' failed during pull: {1}")]
    PullFailed(NodeId, String),

    #[error("Node '{0}' failed to stop: {1}")]
    StopFailed(NodeId, String),

    #[error("Port '{0}' not found on node '{1}'")]
    PortNotFound(String, NodeId),

    #[error("Invalid configuration for node '{0}': {1}")]
    InvalidConfig(NodeId, String),
}

/// Result type for node operations.
pub type NodeResult<T> = Result<T, NodeError>;

/// Context provided to nodes during lifecycle methods.
///
/// NodeContext provides access to runtime services like logging
/// and background task spawning.
pub struct NodeContext {
    /// Node identifier.
    pub id: NodeId,

    /// Logger for this node (placeholder - would use tracing in real impl).
    _logger: (),
}

impl NodeContext {
    /// Create a new node context.
    pub fn new(id: NodeId) -> Self {
        Self { id, _logger: () }
    }

    /// Log an info message.
    pub fn info(&self, message: &str) {
        tracing::info!(node_id = %self.id, "{}", message);
    }

    /// Log a warning.
    pub fn warn(&self, message: &str) {
        tracing::warn!(node_id = %self.id, "{}", message);
    }

    /// Log an error.
    pub fn error(&self, message: &str) {
        tracing::error!(node_id = %self.id, "{}", message);
    }
}

/// Trait for all graph processing nodes.
///
/// Nodes are the fundamental processing units in the RASL graph.
/// They read from input ports, process data, and write to output ports.
///
/// Node Categories:
/// - Source: No inputs, generates frames (e.g., Waveform)
/// - Transform: Has both inputs and outputs (e.g., Color, Compose)
/// - Sink: No outputs, consumes frames (e.g., ConsoleSink)
///
/// Execution Model:
/// 1. start() is called when the scheduler begins
/// 2. pull() is called when the node needs to produce output
/// 3. stop() is called during graceful shutdown
pub trait Node {
    /// Unique node identifier within the graph.
    fn id(&self) -> &str;

    /// Get input ports.
    fn inputs(&self) -> &InputPorts;

    /// Get mutable input ports.
    fn inputs_mut(&mut self) -> &mut InputPorts;

    /// Get output ports.
    fn outputs(&self) -> &OutputPorts;

    /// Get mutable output ports.
    fn outputs_mut(&mut self) -> &mut OutputPorts;

    /// Initialize the node when scheduler starts.
    ///
    /// Called once before any pull() calls. Use this to set up resources,
    /// open connections, or start background tasks.
    fn start(&mut self, ctx: &NodeContext) -> NodeResult<()> {
        Ok(())
    }

    /// Process inputs and produce outputs.
    ///
    /// Called by the scheduler when this node needs to compute.
    /// Read from inputs and write to outputs.
    fn pull(&mut self, tick: &TickContext) -> NodeResult<()>;

    /// Clean up the node during graceful shutdown.
    ///
    /// Called once when the scheduler is stopping. Use this to close
    /// connections, flush buffers, and release resources.
    fn stop(&mut self, ctx: &NodeContext) -> NodeResult<()> {
        Ok(())
    }

    /// Get the pull rate in Hz (for sinks that drive the scheduler).
    ///
    /// Return Some(hz) for rate-driving sinks, None for other nodes.
    fn pull_rate(&self) -> Option<f64> {
        None
    }

    /// Downcast to concrete type for config access.
    fn as_any(&self) -> &dyn Any;

    /// Downcast to concrete type for mutation.
    fn as_any_mut(&mut self) -> &mut dyn Any;
}

impl fmt::Debug for dyn Node {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Node")
            .field("id", &self.id())
            .field("inputs", &self.inputs().names().collect::<Vec<_>>())
            .field("outputs", &self.outputs().names().collect::<Vec<_>>())
            .finish()
    }
}

/// Helper macro for implementing Node trait boilerplate.
#[macro_export]
macro_rules! impl_node_basics {
    ($type:ty, $id:ident, $inputs:ident, $outputs:ident) => {
        fn id(&self) -> &str {
            &self.$id
        }

        fn inputs(&self) -> &$crate::port::InputPorts {
            &self.$inputs
        }

        fn inputs_mut(&mut self) -> &mut $crate::port::InputPorts {
            &mut self.$inputs
        }

        fn outputs(&self) -> &$crate::port::OutputPorts {
            &self.$outputs
        }

        fn outputs_mut(&mut self) -> &mut $crate::port::OutputPorts {
            &mut self.$outputs
        }

        fn as_any(&self) -> &dyn std::any::Any {
            self
        }

        fn as_any_mut(&mut self) -> &mut dyn std::any::Any {
            self
        }
    };
}

#[cfg(test)]
mod tests {
    use super::*;

    struct TestNode {
        id: String,
        inputs: InputPorts,
        outputs: OutputPorts,
        pull_count: usize,
    }

    impl TestNode {
        fn new(id: &str) -> Self {
            Self {
                id: id.to_string(),
                inputs: InputPorts::new(),
                outputs: OutputPorts::new(),
                pull_count: 0,
            }
        }
    }

    impl Node for TestNode {
        impl_node_basics!(TestNode, id, inputs, outputs);

        fn pull(&mut self, _tick: &TickContext) -> NodeResult<()> {
            self.pull_count += 1;
            Ok(())
        }
    }

    #[test]
    fn test_node_trait() {
        let mut node = TestNode::new("test");
        assert_eq!(node.id(), "test");

        let tick = TickContext::default();
        node.pull(&tick).unwrap();
        assert_eq!(node.pull_count, 1);
    }
}
