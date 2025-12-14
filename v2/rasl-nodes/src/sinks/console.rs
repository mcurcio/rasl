//! Console sink node for debugging and logging.
//!
//! Logs incoming frame data to the console.

use rasl_core::frame::Frame;
use rasl_core::node::{Node, NodeContext, NodeResult};
use rasl_core::payload::MatrixPayload;
use rasl_core::port::{InputPort, InputPorts, OutputPorts, PortSpec};
use rasl_core::tick::TickContext;
use tracing::info;

/// Configuration for ConsoleSinkNode.
#[derive(Debug, Clone)]
pub struct ConsoleSinkConfig {
    pub id: String,
    pub input_port: String,
    pub max_channels: usize,
    pub as_bytes: bool,
    pub fps: f64,
    pub include_metadata: bool,
    pub label: Option<String>,
}

impl Default for ConsoleSinkConfig {
    fn default() -> Self {
        Self {
            id: "console".to_string(),
            input_port: "dmx".to_string(),
            max_channels: 16,
            as_bytes: true,
            fps: 30.0,
            include_metadata: true,
            label: None,
        }
    }
}

/// Sink node that logs frame data to the console.
pub struct ConsoleSinkNode {
    id: String,
    inputs: InputPorts,
    outputs: OutputPorts,
    input_port: String,
    max_channels: usize,
    as_bytes: bool,
    fps: f64,
    include_metadata: bool,
    label: String,
    counter: u64,
}

impl ConsoleSinkNode {
    /// Create a new ConsoleSinkNode.
    pub fn new(config: ConsoleSinkConfig) -> Self {
        let mut inputs = InputPorts::new();
        inputs.add(InputPort::new(PortSpec::new(&config.input_port, "matrix")));

        Self {
            id: config.id.clone(),
            inputs,
            outputs: OutputPorts::new(),
            input_port: config.input_port,
            max_channels: config.max_channels,
            as_bytes: config.as_bytes,
            fps: config.fps,
            include_metadata: config.include_metadata,
            label: config.label.unwrap_or_else(|| config.id.clone()),
            counter: 0,
        }
    }

    /// Create with simple defaults.
    pub fn simple(id: &str, fps: f64) -> Self {
        Self::new(ConsoleSinkConfig {
            id: id.to_string(),
            fps,
            ..Default::default()
        })
    }

    fn format_data(&self, payload: &MatrixPayload) -> String {
        let flat = payload.flatten();
        let show_count = flat.len().min(self.max_channels);
        let values: Vec<String> = flat[..show_count]
            .iter()
            .map(|v| {
                if self.as_bytes {
                    format!("{}", (v.clamp(0.0, 1.0) * 255.0).round() as u8)
                } else {
                    format!("{:.3}", v)
                }
            })
            .collect();

        let mut result = format!("[{}]", values.join(", "));
        if flat.len() > show_count {
            result.push_str(&format!(" ... ({} total)", flat.len()));
        }
        result
    }
}

impl Node for ConsoleSinkNode {
    rasl_core::impl_node_basics!(ConsoleSinkNode, id, inputs, outputs);

    fn start(&mut self, ctx: &NodeContext) -> NodeResult<()> {
        info!(
            label = %self.label,
            input_port = %self.input_port,
            max_channels = self.max_channels,
            fps = self.fps,
            "console_sink_started"
        );
        Ok(())
    }

    fn pull(&mut self, tick: &TickContext) -> NodeResult<()> {
        let frame = match self.inputs.get(&self.input_port).and_then(|p| p.read()) {
            Some(f) => f,
            None => return Ok(()),
        };

        self.counter += 1;

        let data_str = self.format_data(&frame.payload);

        if self.include_metadata && !frame.metadata.values.is_empty() {
            info!(
                label = %self.label,
                frame_count = self.counter,
                tick = tick.tick,
                t = format!("{:.3}", tick.t),
                data = %data_str,
                metadata = ?frame.metadata.values,
                "console_sink_frame"
            );
        } else {
            info!(
                label = %self.label,
                frame_count = self.counter,
                tick = tick.tick,
                t = format!("{:.3}", tick.t),
                data = %data_str,
                "console_sink_frame"
            );
        }

        Ok(())
    }

    fn stop(&mut self, ctx: &NodeContext) -> NodeResult<()> {
        info!(
            label = %self.label,
            total_frames = self.counter,
            "console_sink_stopped"
        );
        Ok(())
    }

    fn pull_rate(&self) -> Option<f64> {
        Some(self.fps)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::Array2;

    #[test]
    fn test_console_sink() {
        let mut node = ConsoleSinkNode::simple("test", 30.0);

        // Create input frame
        let data = Array2::from_shape_vec((3, 3), vec![1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0])
            .unwrap();
        let frame = Frame::new("test", MatrixPayload::new(data));
        node.inputs.get("dmx").unwrap().set(frame);

        let tick = TickContext::default();
        node.pull(&tick).unwrap();

        assert_eq!(node.counter, 1);
    }

    #[test]
    fn test_console_sink_pull_rate() {
        let node = ConsoleSinkNode::simple("test", 60.0);
        assert_eq!(node.pull_rate(), Some(60.0));
    }
}
