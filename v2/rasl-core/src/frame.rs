//! Frame type - immutable data container with routing metadata.
//!
//! Frames are the primary data unit flowing through the graph.
//! Each frame contains a payload and metadata for routing/debugging.

use crate::payload::Payload;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

/// Metadata attached to frames for routing and debugging.
#[derive(Debug, Clone, Default)]
pub struct Metadata {
    pub values: HashMap<String, String>,
}

impl Metadata {
    /// Create empty metadata.
    pub fn new() -> Self {
        Self::default()
    }

    /// Create metadata with a single key-value pair.
    pub fn with(key: impl Into<String>, value: impl Into<String>) -> Self {
        let mut m = Self::new();
        m.values.insert(key.into(), value.into());
        m
    }

    /// Get a metadata value.
    pub fn get(&self, key: &str) -> Option<&str> {
        self.values.get(key).map(|s| s.as_str())
    }

    /// Set a metadata value.
    pub fn set(&mut self, key: impl Into<String>, value: impl Into<String>) {
        self.values.insert(key.into(), value.into());
    }
}

/// Immutable frame flowing through the graph.
///
/// Frames carry payloads between nodes along with routing metadata.
/// They are immutable - to modify, create a new frame with `with_payload()`.
#[derive(Clone)]
pub struct Frame<P: Payload> {
    /// Topic for routing (e.g., "waveform.hue_ramp").
    pub topic: String,

    /// Timestamp when the frame was created.
    pub timestamp: f64,

    /// The payload data.
    pub payload: P,

    /// Optional metadata for debugging/routing.
    pub metadata: Arc<Metadata>,
}

impl<P: Payload> Frame<P> {
    /// Create a new frame.
    pub fn new(topic: impl Into<String>, payload: P) -> Self {
        Self {
            topic: topic.into(),
            timestamp: 0.0,
            payload,
            metadata: Arc::new(Metadata::new()),
        }
    }

    /// Create a new frame with timestamp.
    pub fn with_timestamp(topic: impl Into<String>, timestamp: f64, payload: P) -> Self {
        Self {
            topic: topic.into(),
            timestamp,
            payload,
            metadata: Arc::new(Metadata::new()),
        }
    }

    /// Create a new frame with the same metadata but different payload.
    pub fn with_payload<Q: Payload>(&self, payload: Q) -> Frame<Q> {
        Frame {
            topic: self.topic.clone(),
            timestamp: self.timestamp,
            payload,
            metadata: Arc::clone(&self.metadata),
        }
    }

    /// Create a new frame with updated metadata.
    pub fn with_metadata(&self, metadata: Metadata) -> Self {
        Self {
            topic: self.topic.clone(),
            timestamp: self.timestamp,
            payload: self.payload.clone(),
            metadata: Arc::new(metadata),
        }
    }

    /// Create a new frame with a single metadata key-value pair added.
    pub fn with_metadata_value(&self, key: &str, value: &str) -> Self {
        let mut new_metadata = (*self.metadata).clone();
        new_metadata.values.insert(key.to_string(), value.to_string());
        Self {
            topic: self.topic.clone(),
            timestamp: self.timestamp,
            payload: self.payload.clone(),
            metadata: Arc::new(new_metadata),
        }
    }

    /// Get the payload count (number of elements).
    pub fn count(&self) -> usize {
        self.payload.count()
    }

    /// Get the payload channels.
    pub fn channels(&self) -> usize {
        self.payload.channels()
    }
}

impl<P: Payload + std::fmt::Debug> std::fmt::Debug for Frame<P> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Frame")
            .field("topic", &self.topic)
            .field("timestamp", &self.timestamp)
            .field("payload", &self.payload)
            .finish()
    }
}

/// Type-erased frame for storage in heterogeneous collections.
pub enum AnyFrame {
    Matrix(Frame<crate::MatrixPayload>),
    Color(Frame<crate::ColorPayload>),
}

impl AnyFrame {
    /// Get the topic.
    pub fn topic(&self) -> &str {
        match self {
            AnyFrame::Matrix(f) => &f.topic,
            AnyFrame::Color(f) => &f.topic,
        }
    }

    /// Get the timestamp.
    pub fn timestamp(&self) -> f64 {
        match self {
            AnyFrame::Matrix(f) => f.timestamp,
            AnyFrame::Color(f) => f.timestamp,
        }
    }

    /// Get count.
    pub fn count(&self) -> usize {
        match self {
            AnyFrame::Matrix(f) => f.count(),
            AnyFrame::Color(f) => f.count(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::MatrixPayload;

    #[test]
    fn test_frame_creation() {
        let payload = MatrixPayload::from_slice(&[1.0, 2.0, 3.0]);
        let frame = Frame::new("test.topic", payload);
        assert_eq!(frame.topic, "test.topic");
        assert_eq!(frame.count(), 3);
    }

    #[test]
    fn test_frame_with_payload() {
        let payload1 = MatrixPayload::from_slice(&[1.0, 2.0, 3.0]);
        let frame1 = Frame::new("test.topic", payload1);

        let payload2 = MatrixPayload::from_slice(&[4.0, 5.0]);
        let frame2 = frame1.with_payload(payload2);

        assert_eq!(frame2.topic, "test.topic");
        assert_eq!(frame2.count(), 2);
    }
}
