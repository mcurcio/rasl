//! RASL Runtime - Scheduler and execution engine.
//!
//! This crate provides the scheduler that executes RASL graphs:
//!
//! - [`Scheduler`] - Tick-based pull scheduler driven by sink rates
//! - Frame caching and lazy evaluation
//! - Deterministic timing with minimal jitter

pub mod scheduler;

pub use scheduler::Scheduler;
