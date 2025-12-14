//! Compose transform node for interleaving multiple inputs.
//!
//! Combines multiple input ports into a single interleaved output.

use ndarray::Array2;
use rasl_core::color::ColorModel;
use rasl_core::frame::{Frame, Metadata};
use rasl_core::node::{Node, NodeContext, NodeResult};
use rasl_core::payload::MatrixPayload;
use rasl_core::port::{InputPort, InputPorts, OutputPort, OutputPorts, PortSpec};
use rasl_core::tick::TickContext;
use std::collections::HashMap;
use std::sync::Arc;

/// Configuration for ComposeNode.
#[derive(Debug, Clone)]
pub struct ComposeConfig {
    pub id: String,
    pub ports: Vec<String>,
    pub fill: HashMap<String, f32>,
    pub output_type: String,
    pub output_channels: Option<usize>,
}

impl Default for ComposeConfig {
    fn default() -> Self {
        Self {
            id: "compose".to_string(),
            ports: vec!["a".to_string(), "b".to_string(), "c".to_string()],
            fill: HashMap::new(),
            output_type: "array".to_string(),
            output_channels: None,
        }
    }
}

/// Composes multiple inputs into interleaved output.
///
/// Ports are variable-length and resolve from connected sources.
/// Unconnected ports must have a fill value.
pub struct ComposeNode {
    id: String,
    inputs: InputPorts,
    outputs: OutputPorts,
    port_names: Vec<String>,
    fills: HashMap<String, f32>,
    output_type: String,
    resolved_length: Option<usize>,
}

impl ComposeNode {
    /// Create a new ComposeNode.
    pub fn new(config: ComposeConfig) -> Self {
        let mut inputs = InputPorts::new();
        for name in &config.ports {
            inputs.add(InputPort::new(PortSpec::new(name, "matrix")));
        }

        let mut outputs = OutputPorts::new();
        outputs.add(OutputPort::new(PortSpec::new("out", "matrix")));

        Self {
            id: config.id,
            inputs,
            outputs,
            port_names: config.ports,
            fills: config.fill,
            output_type: config.output_type,
            resolved_length: config.output_channels,
        }
    }

    /// Create for HSL composition.
    pub fn hsl(id: &str) -> Self {
        Self::new(ComposeConfig {
            id: id.to_string(),
            ports: vec!["hue".to_string(), "saturation".to_string(), "lightness".to_string()],
            fill: HashMap::new(),
            output_type: "hsl".to_string(),
            output_channels: None,
        })
    }

    /// Create for OkHSL composition.
    pub fn okhsl(id: &str) -> Self {
        Self::new(ComposeConfig {
            id: id.to_string(),
            ports: vec!["hue".to_string(), "saturation".to_string(), "lightness".to_string()],
            fill: HashMap::new(),
            output_type: "okhsl".to_string(),
            output_channels: None,
        })
    }

    /// Set a fill value for a port.
    pub fn with_fill(mut self, port: &str, value: f32) -> Self {
        self.fills.insert(port.to_string(), value);
        self
    }
}

impl Node for ComposeNode {
    rasl_core::impl_node_basics!(ComposeNode, id, inputs, outputs);

    fn pull(&mut self, tick: &TickContext) -> NodeResult<()> {
        let mut buffers: HashMap<String, Option<Vec<f32>>> = HashMap::new();
        let mut count: Option<usize> = self.resolved_length;
        let mut last_frame: Option<Frame<MatrixPayload>> = None;

        // Read all input ports
        for port_name in &self.port_names {
            if let Some(port) = self.inputs.get(port_name) {
                if let Some(frame) = port.read() {
                    let data = frame.payload.flatten();
                    if count.is_none() {
                        count = Some(data.len());
                    }
                    buffers.insert(port_name.clone(), Some(data));
                    last_frame = Some(frame);
                } else {
                    buffers.insert(port_name.clone(), None);
                }
            }
        }

        let count = match count {
            Some(c) => c,
            None => return Ok(()), // No data available
        };

        self.resolved_length = Some(count);

        // Compose output matrix
        let num_ports = self.port_names.len();
        let mut out = Array2::zeros((count, num_ports));

        for (i, name) in self.port_names.iter().enumerate() {
            if let Some(fill_value) = self.fills.get(name) {
                // Use fill value
                for row in 0..count {
                    out[[row, i]] = *fill_value;
                }
            } else if let Some(Some(data)) = buffers.get(name) {
                // Use input data
                let copy_len = data.len().min(count);
                for row in 0..copy_len {
                    out[[row, i]] = data[row];
                }
            }
        }

        // Create output payload
        let payload = MatrixPayload::new(out);

        // Add color model metadata if applicable
        let mut metadata = Metadata::new();
        if let Some(model) = ColorModel::from_str(&self.output_type) {
            metadata.set("color_model", model.as_str());
        }

        let frame = Frame {
            topic: format!("compose.{}", self.id),
            timestamp: tick.wall_time,
            payload,
            metadata: Arc::new(metadata),
        };

        self.outputs.get("out").unwrap().write(frame);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compose_with_fills() {
        let mut node = ComposeNode::okhsl("test")
            .with_fill("saturation", 1.0)
            .with_fill("lightness", 0.5);

        // Provide hue input
        let hue_data = Array2::from_shape_vec((3, 1), vec![0.0, 0.33, 0.66]).unwrap();
        let hue_frame = Frame::new("hue", MatrixPayload::new(hue_data));
        node.inputs.get("hue").unwrap().set(hue_frame);

        let tick = TickContext::default();
        node.pull(&tick).unwrap();

        let out = node.outputs.get("out").unwrap().take().unwrap();
        assert_eq!(out.count(), 3);
        assert_eq!(out.channels(), 3);

        // Check fill values
        let row0 = out.payload.row(0).unwrap();
        assert!((row0[1] - 1.0).abs() < 0.01); // saturation
        assert!((row0[2] - 0.5).abs() < 0.01); // lightness
    }
}
