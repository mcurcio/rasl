//! Port types for node inputs and outputs.
//!
//! Ports are the connection points between nodes. Each node declares
//! its input and output ports with specifications.

use crate::frame::Frame;
use crate::payload::MatrixPayload;
use std::cell::RefCell;
use std::collections::HashMap;

/// Port specification for type checking.
#[derive(Debug, Clone)]
pub struct PortSpec {
    /// Port name.
    pub name: String,

    /// Expected payload domain (e.g., "matrix", "color").
    pub domain: String,

    /// Optional channel count (None = any).
    pub channels: Option<usize>,
}

impl PortSpec {
    /// Create a new port spec.
    pub fn new(name: impl Into<String>, domain: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            domain: domain.into(),
            channels: None,
        }
    }

    /// Create a port spec with channel count.
    pub fn with_channels(
        name: impl Into<String>,
        domain: impl Into<String>,
        channels: usize,
    ) -> Self {
        Self {
            name: name.into(),
            domain: domain.into(),
            channels: Some(channels),
        }
    }
}

/// Input port that receives frames from upstream nodes.
#[derive(Debug)]
pub struct InputPort {
    /// Port specification.
    pub spec: PortSpec,

    /// Current frame (set by scheduler before pull).
    frame: RefCell<Option<Frame<MatrixPayload>>>,
}

impl InputPort {
    /// Create a new input port.
    pub fn new(spec: PortSpec) -> Self {
        Self {
            spec,
            frame: RefCell::new(None),
        }
    }

    /// Read the current frame (consumes it).
    pub fn read(&self) -> Option<Frame<MatrixPayload>> {
        self.frame.borrow_mut().take()
    }

    /// Peek at the current frame without consuming.
    pub fn peek(&self) -> Option<Frame<MatrixPayload>> {
        self.frame.borrow().clone()
    }

    /// Set the frame (called by scheduler).
    pub fn set(&self, frame: Frame<MatrixPayload>) {
        *self.frame.borrow_mut() = Some(frame);
    }

    /// Clear the frame.
    pub fn clear(&self) {
        *self.frame.borrow_mut() = None;
    }

    /// Check if a frame is available.
    pub fn has_frame(&self) -> bool {
        self.frame.borrow().is_some()
    }
}

/// Output port that emits frames to downstream nodes.
#[derive(Debug)]
pub struct OutputPort {
    /// Port specification.
    pub spec: PortSpec,

    /// Current frame (written by node during pull).
    frame: RefCell<Option<Frame<MatrixPayload>>>,
}

impl OutputPort {
    /// Create a new output port.
    pub fn new(spec: PortSpec) -> Self {
        Self {
            spec,
            frame: RefCell::new(None),
        }
    }

    /// Write a frame to the output.
    pub fn write(&self, frame: Frame<MatrixPayload>) {
        *self.frame.borrow_mut() = Some(frame);
    }

    /// Take the written frame (called by scheduler).
    pub fn take(&self) -> Option<Frame<MatrixPayload>> {
        self.frame.borrow_mut().take()
    }

    /// Peek at the written frame.
    pub fn peek(&self) -> Option<Frame<MatrixPayload>> {
        self.frame.borrow().clone()
    }

    /// Clear the output.
    pub fn clear(&self) {
        *self.frame.borrow_mut() = None;
    }
}

/// Collection of input ports.
#[derive(Debug, Default)]
pub struct InputPorts {
    ports: HashMap<String, InputPort>,
}

impl InputPorts {
    /// Create empty input ports.
    pub fn new() -> Self {
        Self::default()
    }

    /// Add an input port.
    pub fn add(&mut self, port: InputPort) {
        self.ports.insert(port.spec.name.clone(), port);
    }

    /// Get a port by name.
    pub fn get(&self, name: &str) -> Option<&InputPort> {
        self.ports.get(name)
    }

    /// Iterate over ports.
    pub fn iter(&self) -> impl Iterator<Item = (&String, &InputPort)> {
        self.ports.iter()
    }

    /// Get port names.
    pub fn names(&self) -> impl Iterator<Item = &String> {
        self.ports.keys()
    }

    /// Check if empty.
    pub fn is_empty(&self) -> bool {
        self.ports.is_empty()
    }

    /// Number of ports.
    pub fn len(&self) -> usize {
        self.ports.len()
    }
}

/// Collection of output ports.
#[derive(Debug, Default)]
pub struct OutputPorts {
    ports: HashMap<String, OutputPort>,
}

impl OutputPorts {
    /// Create empty output ports.
    pub fn new() -> Self {
        Self::default()
    }

    /// Add an output port.
    pub fn add(&mut self, port: OutputPort) {
        self.ports.insert(port.spec.name.clone(), port);
    }

    /// Get a port by name.
    pub fn get(&self, name: &str) -> Option<&OutputPort> {
        self.ports.get(name)
    }

    /// Iterate over ports.
    pub fn iter(&self) -> impl Iterator<Item = (&String, &OutputPort)> {
        self.ports.iter()
    }

    /// Get port names.
    pub fn names(&self) -> impl Iterator<Item = &String> {
        self.ports.keys()
    }

    /// Check if empty.
    pub fn is_empty(&self) -> bool {
        self.ports.is_empty()
    }

    /// Number of ports.
    pub fn len(&self) -> usize {
        self.ports.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_input_port_read() {
        let port = InputPort::new(PortSpec::new("test", "matrix"));
        assert!(port.read().is_none());

        let payload = MatrixPayload::from_slice(&[1.0, 2.0]);
        let frame = Frame::new("test", payload);
        port.set(frame);

        assert!(port.has_frame());
        let read = port.read();
        assert!(read.is_some());
        assert!(!port.has_frame());
    }

    #[test]
    fn test_output_port_write() {
        let port = OutputPort::new(PortSpec::new("out", "matrix"));

        let payload = MatrixPayload::from_slice(&[1.0, 2.0]);
        let frame = Frame::new("test", payload);
        port.write(frame);

        let taken = port.take();
        assert!(taken.is_some());
        assert!(port.take().is_none());
    }
}
