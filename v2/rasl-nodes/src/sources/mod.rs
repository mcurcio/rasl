//! Source nodes - data generators.

pub mod waveform;
pub mod literal;
pub mod sacn;

pub use waveform::{WaveformConfig, WaveformNode};
pub use literal::{LiteralConfig, LiteralNode, PayloadKind};
pub use sacn::{SacnSourceConfig, SacnSourceNode};
