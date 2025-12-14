//! RASL Nodes - Built-in node library.
//!
//! This crate provides the standard node implementations:
//!
//! - Sources: Waveform, Literal
//! - Transforms: Color, Compose, Math
//! - Sinks: ConsoleSink

pub mod sources;
pub mod transforms;
pub mod sinks;

pub use sources::{LiteralNode, WaveformNode};
pub use transforms::{ColorNode, ComposeNode};
pub use sinks::ConsoleSinkNode;
