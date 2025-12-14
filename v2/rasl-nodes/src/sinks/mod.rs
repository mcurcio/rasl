//! Sink nodes - output handlers.

pub mod console;
pub mod ddp;

pub use console::{ConsoleSinkConfig, ConsoleSinkNode};
pub use ddp::{DdpSinkConfig, DdpSinkNode};
