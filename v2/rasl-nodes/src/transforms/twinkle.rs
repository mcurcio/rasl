//! TwinkleEffect transform node.
//!
//! Applies TwinkleFOX-style modulation to incoming color data.
//! Each pixel gets a random phase offset and speed multiplier, creating
//! organic, non-synchronized twinkling.

use ndarray::Array2;
use rasl_core::color::{convert_color, ColorModel};
use rasl_core::frame::Frame;
use rasl_core::node::{Node, NodeContext, NodeResult};
use rasl_core::payload::{MatrixPayload, Payload};
use rasl_core::port::{InputPort, InputPorts, OutputPort, OutputPorts, PortSpec};
use rasl_core::tick::TickContext;
use rasl_core::impl_node_basics;

/// Twinkle mode determines how the effect is applied.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TwinkleMode {
    /// Multiply RGB by envelope → fade to black (classic twinkle)
    Brightness,
    /// Reduce saturation by envelope → fade to white (sparkle)
    Whiteness,
}

impl TwinkleMode {
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "brightness" => Some(TwinkleMode::Brightness),
            "whiteness" => Some(TwinkleMode::Whiteness),
            _ => None,
        }
    }
}

/// Configuration for TwinkleEffect node.
#[derive(Debug, Clone)]
pub struct TwinkleEffectConfig {
    pub id: String,
    pub seed: u64,
    pub mode: TwinkleMode,
    pub frequency_hz: f32,
    pub attack_ratio: f32,
    pub min_speed: f32,
    pub max_speed: f32,
}

impl Default for TwinkleEffectConfig {
    fn default() -> Self {
        Self {
            id: "twinkle".to_string(),
            seed: 42,
            mode: TwinkleMode::Brightness,
            frequency_hz: 0.3,
            attack_ratio: 0.33,
            min_speed: 1.0,
            max_speed: 3.0,
        }
    }
}

/// TwinkleEffect transform node.
///
/// Applies per-pixel random phase offsets and speed multipliers to create
/// organic, non-synchronized twinkling effects.
pub struct TwinkleEffectNode {
    id: String,
    inputs: InputPorts,
    outputs: OutputPorts,
    
    seed: u64,
    mode: TwinkleMode,
    frequency_hz: f32,
    attack_ratio: f32,
    min_speed: f32,
    max_speed: f32,
    
    // Per-pixel random values (initialized on first frame)
    phase_offsets: Option<Vec<f32>>,
    speed_multipliers: Option<Vec<f32>>,
    num_pixels: Option<usize>,
}

impl TwinkleEffectNode {
    pub fn new(config: TwinkleEffectConfig) -> Self {
        let mut inputs = InputPorts::new();
        inputs.add(InputPort::new(PortSpec::new("input", "color")));
        
        let mut outputs = OutputPorts::new();
        outputs.add(OutputPort::new(PortSpec::new("out", "color")));
        
        Self {
            id: config.id,
            inputs,
            outputs,
            seed: config.seed,
            mode: config.mode,
            frequency_hz: config.frequency_hz,
            attack_ratio: config.attack_ratio,
            min_speed: config.min_speed,
            max_speed: config.max_speed,
            phase_offsets: None,
            speed_multipliers: None,
            num_pixels: None,
        }
    }
    
    /// Initialize per-pixel random values for given pixel count.
    fn initialize_for_size(&mut self, num_pixels: usize) {
        if self.num_pixels == Some(num_pixels) {
            return; // Already initialized for this size
        }
        
        self.num_pixels = Some(num_pixels);
        
        // Simple PCG-style RNG for deterministic per-pixel values
        let mut phase_offsets = Vec::with_capacity(num_pixels);
        let mut speed_multipliers = Vec::with_capacity(num_pixels);
        
        // Phase offsets RNG (seed)
        let mut state_phase = self.seed;
        for _ in 0..num_pixels {
            state_phase = pcg_next(&mut state_phase);
            phase_offsets.push((state_phase as f32) / (u64::MAX as f32));
        }
        
        // Speed multipliers RNG (seed + 1)
        let mut state_speed = self.seed.wrapping_add(1);
        let speed_range = self.max_speed - self.min_speed;
        for _ in 0..num_pixels {
            state_speed = pcg_next(&mut state_speed);
            let rand_val = (state_speed as f32) / (u64::MAX as f32);
            speed_multipliers.push(rand_val * speed_range + self.min_speed);
        }
        
        self.phase_offsets = Some(phase_offsets);
        self.speed_multipliers = Some(speed_multipliers);
    }
}

/// Simple PCG-style random number generator step.
fn pcg_next(state: &mut u64) -> u64 {
    let old = *state;
    *state = old.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
    let xorshifted = (((old >> 18) ^ old) >> 27) as u32;
    let rot = (old >> 59) as u32;
    ((xorshifted >> rot) | (xorshifted << ((!rot).wrapping_add(1) & 31))) as u64
}

/// Attack-decay waveform (fast attack, slow decay).
/// This is the classic TwinkleFOX brightness envelope.
fn attack_decay_wave(phase: f32, attack_ratio: f32) -> f32 {
    let phase = phase % 1.0;
    if phase < attack_ratio {
        phase / attack_ratio // Attack: ramp up
    } else {
        1.0 - (phase - attack_ratio) / (1.0 - attack_ratio) // Decay: ramp down
    }
}

impl Node for TwinkleEffectNode {
    impl_node_basics!(TwinkleEffectNode, id, inputs, outputs);
    
    fn pull(&mut self, tick: &TickContext) -> NodeResult<()> {
        let frame = match self.inputs.get("input").and_then(|p| p.read()) {
            Some(f) => f,
            None => return Ok(()),
        };
        
        let payload = &frame.payload;
        let data = payload.as_array();
        let (num_pixels, channels) = (data.nrows(), data.ncols());
        
        if num_pixels == 0 || channels < 3 {
            // Pass through unchanged
            if let Some(out) = self.outputs.get("out") {
                out.write(frame);
            }
            return Ok(());
        }
        
        // Initialize per-pixel values if needed
        self.initialize_for_size(num_pixels);
        let phase_offsets = self.phase_offsets.as_ref().unwrap();
        let speed_multipliers = self.speed_multipliers.as_ref().unwrap();
        
        // Calculate current phase for each pixel using scheduler time
        let t = tick.t as f32;
        let base_phase = t * self.frequency_hz;
        
        // Get source color model from metadata
        let src_model = frame.metadata.values.get("color_model")
            .and_then(|s| ColorModel::from_str(s))
            .unwrap_or(ColorModel::Srgb);
        
        let mut result_data = data.to_owned();
        
        match self.mode {
            TwinkleMode::Brightness => {
                // Brightness mode: multiply RGB by envelope → fade to black
                // Convert to sRGB if needed (OkHSL has numerical instability at low lightness)
                let rgb_data = if src_model != ColorModel::Srgb {
                    convert_color(data, src_model, ColorModel::Srgb)
                } else {
                    data.to_owned()
                };
                
                let mut output = rgb_data;
                for i in 0..num_pixels {
                    let pixel_phase = (base_phase * speed_multipliers[i] + phase_offsets[i]) % 1.0;
                    let envelope = attack_decay_wave(pixel_phase, self.attack_ratio);
                    
                    // Apply envelope to RGB channels
                    for c in 0..3.min(channels) {
                        output[[i, c]] *= envelope;
                    }
                }
                
                result_data = output;
                
                // Output as sRGB
                let output_frame = Frame::new(&self.id, MatrixPayload::new(result_data))
                    .with_metadata_value("color_model", "srgb");
                
                if let Some(out) = self.outputs.get("out") {
                    out.write(output_frame);
                }
            }
            TwinkleMode::Whiteness => {
                // Whiteness mode: reduce saturation by envelope → fade to white
                // Convert to OkHSL if needed
                let hsl_data = if src_model != ColorModel::Okhsl {
                    convert_color(data, src_model, ColorModel::Okhsl)
                } else {
                    data.to_owned()
                };
                
                let mut output = hsl_data;
                for i in 0..num_pixels {
                    let pixel_phase = (base_phase * speed_multipliers[i] + phase_offsets[i]) % 1.0;
                    let envelope = attack_decay_wave(pixel_phase, self.attack_ratio);
                    
                    // Reduce saturation (channel 1) by envelope
                    if channels >= 2 {
                        output[[i, 1]] *= 1.0 - envelope;
                    }
                }
                
                result_data = output;
                
                // Output as OkHSL
                let output_frame = Frame::new(&self.id, MatrixPayload::new(result_data))
                    .with_metadata_value("color_model", "okhsl");
                
                if let Some(out) = self.outputs.get("out") {
                    out.write(output_frame);
                }
            }
        }
        
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_attack_decay_wave() {
        // At phase 0, should be 0
        assert!((attack_decay_wave(0.0, 0.33) - 0.0).abs() < 0.01);
        
        // At attack_ratio, should be 1
        assert!((attack_decay_wave(0.33, 0.33) - 1.0).abs() < 0.01);
        
        // At phase 1, should be 0
        assert!((attack_decay_wave(0.99, 0.33) - 0.0).abs() < 0.05);
    }
    
    #[test]
    fn test_twinkle_mode_from_str() {
        assert_eq!(TwinkleMode::from_str("brightness"), Some(TwinkleMode::Brightness));
        assert_eq!(TwinkleMode::from_str("whiteness"), Some(TwinkleMode::Whiteness));
        assert_eq!(TwinkleMode::from_str("BRIGHTNESS"), Some(TwinkleMode::Brightness));
        assert_eq!(TwinkleMode::from_str("invalid"), None);
    }
    
    #[test]
    fn test_twinkle_effect_initialization() {
        let config = TwinkleEffectConfig {
            id: "test".to_string(),
            seed: 12345,
            ..Default::default()
        };
        let mut node = TwinkleEffectNode::new(config);
        
        // Initialize for 10 pixels
        node.initialize_for_size(10);
        
        assert!(node.phase_offsets.is_some());
        assert!(node.speed_multipliers.is_some());
        assert_eq!(node.phase_offsets.as_ref().unwrap().len(), 10);
        assert_eq!(node.speed_multipliers.as_ref().unwrap().len(), 10);
        
        // Check phase offsets are in [0, 1)
        for &phase in node.phase_offsets.as_ref().unwrap() {
            assert!(phase >= 0.0 && phase < 1.0);
        }
        
        // Check speed multipliers are in [min_speed, max_speed]
        for &speed in node.speed_multipliers.as_ref().unwrap() {
            assert!(speed >= node.min_speed && speed <= node.max_speed);
        }
    }
}
