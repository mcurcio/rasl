//! RASL Core - Frame, Payload, Node, and Graph types
//!
//! This crate provides the foundational types for the RASL real-time
//! animation system:
//!
//! - [`Frame`] - Immutable data container with routing metadata
//! - [`Payload`] - Trait for frame payloads (Matrix, Color)
//! - [`Node`] - Trait for graph processing nodes
//! - [`Graph`] - DAG structure and execution plan

pub mod color;
pub mod frame;
pub mod graph;
pub mod node;
pub mod payload;
pub mod port;
pub mod tick;

pub use color::{ColorModel, ColorPayload};
pub use frame::Frame;
pub use graph::{Edge, ExecutionPlan, GraphBuilder};
pub use node::{Node, NodeContext, NodeId};
pub use payload::{MatrixPayload, Payload};
pub use port::{InputPort, OutputPort, PortSpec};
pub use tick::TickContext;
