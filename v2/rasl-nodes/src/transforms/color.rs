//! Universal color conversion node.
//!
//! Converts between color spaces using the color module.

use ndarray::Array2;
use rasl_core::color::{convert_color, ColorModel, ColorPayload};
use rasl_core::frame::Frame;
use rasl_core::node::{Node, NodeContext, NodeResult};
use rasl_core::payload::{MatrixPayload, Payload};
use rasl_core::port::{InputPort, InputPorts, OutputPort, OutputPorts, PortSpec};
use rasl_core::tick::TickContext;

/// Configuration for ColorNode.
#[derive(Debug, Clone)]
pub struct ColorConfig {
    pub id: String,
    pub model: ColorModel,
}

impl Default for ColorConfig {
    fn default() -> Self {
        Self {
            id: "color".to_string(),
            model: ColorModel::Srgb,
        }
    }
}

/// Universal color space converter.
///
/// Converts any input to the specified color model.
pub struct ColorNode {
    id: String,
    inputs: InputPorts,
    outputs: OutputPorts,
    target_model: ColorModel,
}

impl ColorNode {
    /// Create a new ColorNode.
    pub fn new(config: ColorConfig) -> Self {
        let mut inputs = InputPorts::new();
        inputs.add(InputPort::new(PortSpec::new("color", "color")));

        let mut outputs = OutputPorts::new();
        outputs.add(OutputPort::new(PortSpec::new("color", "color")));

        Self {
            id: config.id,
            inputs,
            outputs,
            target_model: config.model,
        }
    }

    /// Create with target model.
    pub fn with_model(id: &str, model: ColorModel) -> Self {
        Self::new(ColorConfig {
            id: id.to_string(),
            model,
        })
    }

    /// Create RGB output node.
    pub fn to_rgb(id: &str) -> Self {
        Self::with_model(id, ColorModel::Srgb)
    }
}

impl Node for ColorNode {
    rasl_core::impl_node_basics!(ColorNode, id, inputs, outputs);

    fn pull(&mut self, tick: &TickContext) -> NodeResult<()> {
        let frame = match self.inputs.get("color").and_then(|p| p.read()) {
            Some(f) => f,
            None => return Ok(()),
        };

        // Get source model from metadata or assume sRGB
        let src_model = frame
            .metadata
            .get("color_model")
            .and_then(|s| ColorModel::from_str(s))
            .unwrap_or(ColorModel::Srgb);

        // Convert color
        let converted = convert_color(frame.payload.as_array(), src_model, self.target_model);
        let payload = MatrixPayload::new(converted);

        // Create output frame with model metadata
        let mut metadata = (*frame.metadata).clone();
        metadata.set("color_model", self.target_model.as_str());

        let out_frame = Frame {
            topic: frame.topic.clone(),
            timestamp: tick.wall_time,
            payload,
            metadata: std::sync::Arc::new(metadata),
        };

        self.outputs.get("color").unwrap().write(out_frame);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_color_node_passthrough() {
        let mut node = ColorNode::to_rgb("test");

        // Create input frame
        let data = Array2::from_shape_vec((1, 3), vec![1.0, 0.0, 0.0]).unwrap();
        let payload = MatrixPayload::new(data);
        let frame = Frame::new("test", payload);

        node.inputs.get("color").unwrap().set(frame);

        let tick = TickContext::default();
        node.pull(&tick).unwrap();

        let out = node.outputs.get("color").unwrap().take();
        assert!(out.is_some());
    }
}
