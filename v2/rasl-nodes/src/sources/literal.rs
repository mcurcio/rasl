//! Literal source node - produces time-invariant payloads.
//!
//! Outputs a constant payload parsed from config.

use ndarray::Array2;
use rasl_core::color::{ColorModel, ColorPayload};
use rasl_core::frame::Frame;
use rasl_core::node::{Node, NodeContext, NodeResult};
use rasl_core::payload::MatrixPayload;
use rasl_core::port::{InputPorts, OutputPort, OutputPorts, PortSpec};
use rasl_core::tick::TickContext;

/// Payload kind for literal nodes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PayloadKind {
    Matrix,
    Color,
}

impl PayloadKind {
    /// Parse from string.
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "matrix" | "array" => Some(Self::Matrix),
            "color" => Some(Self::Color),
            _ => None,
        }
    }
}

/// Configuration for LiteralNode.
#[derive(Debug, Clone)]
pub struct LiteralConfig {
    pub id: String,
    pub kind: PayloadKind,
    pub color_model: Option<ColorModel>,
    pub data: Vec<Vec<f32>>,
}

/// Source node that outputs a constant literal payload.
pub struct LiteralNode {
    id: String,
    inputs: InputPorts,
    outputs: OutputPorts,
    payload: MatrixPayload,
    color_model: Option<ColorModel>,
}

impl LiteralNode {
    /// Create a new LiteralNode.
    pub fn new(config: LiteralConfig) -> Self {
        let mut outputs = OutputPorts::new();
        outputs.add(OutputPort::new(PortSpec::new("out", "matrix")));

        // Build payload from data
        let rows = config.data.len();
        let cols = if rows > 0 { config.data[0].len() } else { 0 };
        let flat: Vec<f32> = config.data.into_iter().flatten().collect();
        let data = if rows > 0 && cols > 0 {
            Array2::from_shape_vec((rows, cols), flat).expect("literal data shape should be valid")
        } else {
            Array2::zeros((0, 0))
        };

        Self {
            id: config.id,
            inputs: InputPorts::new(),
            outputs,
            payload: MatrixPayload::new(data),
            color_model: config.color_model,
        }
    }

    /// Create from a simple 2D array.
    pub fn from_array(id: &str, data: Vec<Vec<f32>>) -> Self {
        Self::new(LiteralConfig {
            id: id.to_string(),
            kind: PayloadKind::Matrix,
            color_model: None,
            data,
        })
    }

    /// Create a color literal.
    pub fn color(id: &str, model: ColorModel, data: Vec<Vec<f32>>) -> Self {
        Self::new(LiteralConfig {
            id: id.to_string(),
            kind: PayloadKind::Color,
            color_model: Some(model),
            data,
        })
    }
}

impl Node for LiteralNode {
    rasl_core::impl_node_basics!(LiteralNode, id, inputs, outputs);

    fn pull(&mut self, tick: &TickContext) -> NodeResult<()> {
        let frame = Frame::with_timestamp(
            format!("literal.{}", self.id),
            tick.wall_time,
            self.payload.clone(),
        );
        self.outputs.get("out").unwrap().write(frame);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_literal_node() {
        let mut node = LiteralNode::from_array("test", vec![vec![1.0, 0.0, 0.0], vec![0.0, 1.0, 0.0]]);

        let tick = TickContext::default();
        node.pull(&tick).unwrap();

        let frame = node.outputs.get("out").unwrap().take().unwrap();
        assert_eq!(frame.count(), 2);
        assert_eq!(frame.channels(), 3);
    }

    #[test]
    fn test_literal_color() {
        let mut node = LiteralNode::color(
            "test",
            ColorModel::Hsl,
            vec![vec![0.0, 1.0, 0.5], vec![0.33, 1.0, 0.5]],
        );

        let tick = TickContext::default();
        node.pull(&tick).unwrap();

        let frame = node.outputs.get("out").unwrap().take().unwrap();
        assert_eq!(frame.count(), 2);
    }
}
