//! Waveform generator source node.
//!
//! Generates various waveform shapes with per-channel phase and speed
//! modulation support.

use ndarray::Array2;
use rasl_core::frame::Frame;
use rasl_core::node::{Node, NodeContext, NodeResult};
use rasl_core::payload::MatrixPayload;
use rasl_core::port::{InputPort, InputPorts, OutputPort, OutputPorts, PortSpec};
use rasl_core::tick::TickContext;
use std::f32::consts::PI;

/// Waveform shape.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WaveShape {
    Sine,
    Triangle,
    Sawtooth,
    AttackDecay,
    Square,
}

impl WaveShape {
    /// Parse from string.
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "sine" => Some(Self::Sine),
            "triangle" => Some(Self::Triangle),
            "sawtooth" => Some(Self::Sawtooth),
            "attack_decay" => Some(Self::AttackDecay),
            "square" => Some(Self::Square),
            _ => None,
        }
    }
}

impl Default for WaveShape {
    fn default() -> Self {
        Self::Sine
    }
}

/// Configuration for WaveformNode.
#[derive(Debug, Clone)]
pub struct WaveformConfig {
    pub id: String,
    pub output_channels: usize,
    pub shape: WaveShape,
    pub frequency_hz: f64,
    pub attack_ratio: f32,
    pub duty: f32,
}

impl Default for WaveformConfig {
    fn default() -> Self {
        Self {
            id: "waveform".to_string(),
            output_channels: 512,
            shape: WaveShape::Sine,
            frequency_hz: 1.0,
            attack_ratio: 0.33,
            duty: 0.5,
        }
    }
}

/// Source node that generates configurable waveforms.
///
/// Generates per-channel waveforms with optional phase offset and speed
/// modulation inputs. This enables effects like twinkle where each LED
/// has its own phase and speed.
pub struct WaveformNode {
    id: String,
    inputs: InputPorts,
    outputs: OutputPorts,
    config: WaveformConfig,
}

impl WaveformNode {
    /// Create a new WaveformNode.
    pub fn new(config: WaveformConfig) -> Self {
        let mut inputs = InputPorts::new();
        inputs.add(InputPort::new(PortSpec::new("phase", "matrix")));
        inputs.add(InputPort::new(PortSpec::new("speed", "matrix")));

        let mut outputs = OutputPorts::new();
        outputs.add(OutputPort::new(PortSpec::new("out", "matrix")));

        Self {
            id: config.id.clone(),
            inputs,
            outputs,
            config,
        }
    }

    /// Apply the configured waveform shape.
    fn apply_shape(&self, phase: &[f32]) -> Vec<f32> {
        match self.config.shape {
            WaveShape::Sine => sine_wave(phase),
            WaveShape::Triangle => triangle_wave(phase),
            WaveShape::Sawtooth => sawtooth_wave(phase),
            WaveShape::AttackDecay => attack_decay_wave(phase, self.config.attack_ratio),
            WaveShape::Square => square_wave(phase, self.config.duty),
        }
    }
}

impl Node for WaveformNode {
    rasl_core::impl_node_basics!(WaveformNode, id, inputs, outputs);

    fn pull(&mut self, tick: &TickContext) -> NodeResult<()> {
        let t = tick.t;
        let channels = self.config.output_channels;

        // Base phase for all channels
        let base_phase = ((self.config.frequency_hz * t) % 1.0) as f32;

        // Read optional modulation inputs
        let phase_offsets: Option<Vec<f32>> = self
            .inputs
            .get("phase")
            .and_then(|p| p.read())
            .map(|f| f.payload.flatten());

        let speed_multipliers: Option<Vec<f32>> = self
            .inputs
            .get("speed")
            .and_then(|p| p.read())
            .map(|f| f.payload.flatten());

        // Compute per-channel phase
        let mut phase: Vec<f32> = vec![base_phase; channels];

        // Apply speed multipliers
        if let Some(speeds) = speed_multipliers {
            for i in 0..channels {
                let speed = speeds.get(i % speeds.len()).copied().unwrap_or(1.0);
                phase[i] = (base_phase * speed) % 1.0;
            }
        }

        // Apply phase offsets
        if let Some(offsets) = phase_offsets {
            for i in 0..channels {
                let offset = offsets.get(i % offsets.len()).copied().unwrap_or(0.0);
                phase[i] = (phase[i] + offset) % 1.0;
            }
        }

        // Generate waveform
        let values = self.apply_shape(&phase);

        // Create output frame
        let data = Array2::from_shape_vec((channels, 1), values)
            .expect("waveform output shape should be valid");
        let payload = MatrixPayload::new(data);
        let frame = Frame::with_timestamp(format!("waveform.{}", self.id), tick.wall_time, payload);

        self.outputs.get("out").unwrap().write(frame);
        Ok(())
    }
}

// Waveform functions

fn sine_wave(phase: &[f32]) -> Vec<f32> {
    phase
        .iter()
        .map(|p| ((p * 2.0 * PI).sin() + 1.0) / 2.0)
        .collect()
}

fn triangle_wave(phase: &[f32]) -> Vec<f32> {
    phase
        .iter()
        .map(|p| {
            if *p < 0.5 {
                p * 2.0
            } else {
                2.0 - p * 2.0
            }
        })
        .collect()
}

fn sawtooth_wave(phase: &[f32]) -> Vec<f32> {
    phase.to_vec()
}

fn attack_decay_wave(phase: &[f32], attack_ratio: f32) -> Vec<f32> {
    phase
        .iter()
        .map(|p| {
            if *p < attack_ratio {
                p / attack_ratio
            } else {
                1.0 - (p - attack_ratio) / (1.0 - attack_ratio)
            }
        })
        .collect()
}

fn square_wave(phase: &[f32], duty: f32) -> Vec<f32> {
    phase
        .iter()
        .map(|p| if *p < duty { 1.0 } else { 0.0 })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_waveform_sine() {
        let config = WaveformConfig {
            id: "test".to_string(),
            output_channels: 4,
            shape: WaveShape::Sine,
            frequency_hz: 1.0,
            ..Default::default()
        };
        let mut node = WaveformNode::new(config);

        let tick = TickContext::new(1, 0.0, 0.0, 0.0);
        node.pull(&tick).unwrap();

        let frame = node.outputs.get("out").unwrap().take();
        assert!(frame.is_some());
        assert_eq!(frame.unwrap().count(), 4);
    }

    #[test]
    fn test_waveform_sawtooth() {
        let config = WaveformConfig {
            id: "test".to_string(),
            output_channels: 4,
            shape: WaveShape::Sawtooth,
            frequency_hz: 1.0,
            ..Default::default()
        };
        let mut node = WaveformNode::new(config);

        let tick = TickContext::new(1, 0.5, 0.0, 0.5);
        node.pull(&tick).unwrap();

        let frame = node.outputs.get("out").unwrap().take().unwrap();
        // At t=0.5 with freq=1.0, phase should be 0.5
        let value = frame.payload.row(0).unwrap()[0];
        assert!((value - 0.5).abs() < 0.01);
    }
}
