//! Color payload types and conversion.
//!
//! ColorPayload wraps color data with a model tag indicating the color space.
//! Supports sRGB, HSL, OKLCH, Oklab, OkHSL, OkHSV.

use crate::payload::{MatrixPayload, Payload};
use ndarray::{Array2, ArrayView2};
use std::f32::consts::PI;
use std::fmt;

/// Supported color models.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ColorModel {
    Srgb,
    Hsl,
    Oklch,
    Oklab,
    Okhsl,
    Okhsv,
    Linear,
}

impl ColorModel {
    /// Parse a color model from string.
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "srgb" | "rgb" => Some(Self::Srgb),
            "hsl" => Some(Self::Hsl),
            "oklch" => Some(Self::Oklch),
            "oklab" => Some(Self::Oklab),
            "okhsl" => Some(Self::Okhsl),
            "okhsv" => Some(Self::Okhsv),
            "linear" | "linear_rgb" => Some(Self::Linear),
            _ => None,
        }
    }

    /// Get the string name of this model.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Srgb => "srgb",
            Self::Hsl => "hsl",
            Self::Oklch => "oklch",
            Self::Oklab => "oklab",
            Self::Okhsl => "okhsl",
            Self::Okhsv => "okhsv",
            Self::Linear => "linear",
        }
    }
}

impl Default for ColorModel {
    fn default() -> Self {
        Self::Srgb
    }
}

/// Color signal frame with color model tag.
///
/// ColorPayload wraps color data with a model tag indicating the color space.
/// Use `to_model()` to convert between color spaces.
#[derive(Clone)]
pub struct ColorPayload {
    data: MatrixPayload,
    model: ColorModel,
}

impl ColorPayload {
    /// Create a new ColorPayload.
    pub fn new(data: MatrixPayload, model: ColorModel) -> Self {
        Self { data, model }
    }

    /// Create from a 2D array with model.
    pub fn from_array(data: Array2<f32>, model: ColorModel) -> Self {
        Self {
            data: MatrixPayload::new(data),
            model,
        }
    }

    /// Create from nested vectors with model.
    pub fn from_vec2(data: Vec<Vec<f32>>, model: ColorModel) -> Self {
        Self {
            data: MatrixPayload::from_vec2(data),
            model,
        }
    }

    /// Get the color model.
    pub fn model(&self) -> ColorModel {
        self.model
    }

    /// Get the underlying matrix payload.
    pub fn matrix(&self) -> &MatrixPayload {
        &self.data
    }

    /// Convert to a different color model.
    pub fn to_model(&self, target: ColorModel) -> Self {
        if self.model == target {
            return self.clone();
        }

        let converted = convert_color(self.data.as_array(), self.model, target);
        Self {
            data: MatrixPayload::new(converted),
            model: target,
        }
    }

    /// Convert to sRGB.
    pub fn to_srgb(&self) -> Self {
        self.to_model(ColorModel::Srgb)
    }

    /// Get as bytes (0-255 range).
    pub fn to_bytes(&self) -> Vec<u8> {
        let srgb = self.to_srgb();
        srgb.data
            .flatten()
            .iter()
            .map(|v| (v.clamp(0.0, 1.0) * 255.0).round() as u8)
            .collect()
    }
}

impl Payload for ColorPayload {
    fn count(&self) -> usize {
        self.data.count()
    }

    fn channels(&self) -> usize {
        self.data.channels()
    }

    fn as_array(&self) -> ArrayView2<f32> {
        self.data.as_array()
    }

    fn domain(&self) -> &'static str {
        "color"
    }
}

impl fmt::Debug for ColorPayload {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "ColorPayload<{}, {}x{}>",
            self.model.as_str(),
            self.count(),
            self.channels()
        )
    }
}

/// Convert color data between models.
pub fn convert_color(data: ArrayView2<f32>, from: ColorModel, to: ColorModel) -> Array2<f32> {
    if from == to {
        return data.to_owned();
    }

    // Convert to sRGB as intermediate
    let srgb = match from {
        ColorModel::Srgb => data.to_owned(),
        ColorModel::Hsl => hsl_to_srgb(data),
        ColorModel::Oklch => oklch_to_srgb(data),
        ColorModel::Oklab => oklab_to_srgb(data),
        ColorModel::Okhsl => okhsl_to_srgb(data),
        ColorModel::Okhsv => okhsv_to_srgb(data),
        ColorModel::Linear => linear_to_srgb(data),
    };

    // Convert from sRGB to target
    match to {
        ColorModel::Srgb => srgb,
        ColorModel::Hsl => srgb_to_hsl(srgb.view()),
        ColorModel::Oklch => srgb_to_oklch(srgb.view()),
        ColorModel::Oklab => srgb_to_oklab(srgb.view()),
        ColorModel::Okhsl => srgb_to_okhsl(srgb.view()),
        ColorModel::Okhsv => srgb_to_okhsv(srgb.view()),
        ColorModel::Linear => srgb_to_linear(srgb.view()),
    }
}

// ============================================================================
// Color conversion functions
// ============================================================================

fn srgb_to_linear(data: ArrayView2<f32>) -> Array2<f32> {
    data.mapv(|v| {
        if v <= 0.04045 {
            v / 12.92
        } else {
            ((v + 0.055) / 1.055).powf(2.4)
        }
    })
}

fn linear_to_srgb(data: ArrayView2<f32>) -> Array2<f32> {
    data.mapv(|v| {
        if v <= 0.0031308 {
            v * 12.92
        } else {
            1.055 * v.powf(1.0 / 2.4) - 0.055
        }
    })
}

fn srgb_to_hsl(data: ArrayView2<f32>) -> Array2<f32> {
    let rows = data.nrows();
    let mut result = Array2::zeros((rows, 3));

    for i in 0..rows {
        let r = data[[i, 0]];
        let g = data[[i, 1]];
        let b = data[[i, 2]];

        let max = r.max(g).max(b);
        let min = r.min(g).min(b);
        let l = (max + min) / 2.0;

        if (max - min).abs() < 1e-10 {
            result[[i, 0]] = 0.0;
            result[[i, 1]] = 0.0;
            result[[i, 2]] = l;
        } else {
            let d = max - min;
            let s = if l > 0.5 {
                d / (2.0 - max - min)
            } else {
                d / (max + min)
            };

            let h = if (max - r).abs() < 1e-10 {
                (g - b) / d + if g < b { 6.0 } else { 0.0 }
            } else if (max - g).abs() < 1e-10 {
                (b - r) / d + 2.0
            } else {
                (r - g) / d + 4.0
            };

            result[[i, 0]] = h / 6.0;
            result[[i, 1]] = s;
            result[[i, 2]] = l;
        }
    }

    result
}

fn hsl_to_srgb(data: ArrayView2<f32>) -> Array2<f32> {
    let rows = data.nrows();
    let mut result = Array2::zeros((rows, 3));

    for i in 0..rows {
        let h = data[[i, 0]];
        let s = data[[i, 1]];
        let l = data[[i, 2]];

        if s.abs() < 1e-10 {
            result[[i, 0]] = l;
            result[[i, 1]] = l;
            result[[i, 2]] = l;
        } else {
            let q = if l < 0.5 {
                l * (1.0 + s)
            } else {
                l + s - l * s
            };
            let p = 2.0 * l - q;

            result[[i, 0]] = hue_to_rgb(p, q, h + 1.0 / 3.0);
            result[[i, 1]] = hue_to_rgb(p, q, h);
            result[[i, 2]] = hue_to_rgb(p, q, h - 1.0 / 3.0);
        }
    }

    result
}

fn hue_to_rgb(p: f32, q: f32, mut t: f32) -> f32 {
    if t < 0.0 {
        t += 1.0;
    }
    if t > 1.0 {
        t -= 1.0;
    }
    if t < 1.0 / 6.0 {
        return p + (q - p) * 6.0 * t;
    }
    if t < 1.0 / 2.0 {
        return q;
    }
    if t < 2.0 / 3.0 {
        return p + (q - p) * (2.0 / 3.0 - t) * 6.0;
    }
    p
}

// Oklab conversion matrices
const M1: [[f32; 3]; 3] = [
    [0.4122214708, 0.5363325363, 0.0514459929],
    [0.2119034982, 0.6806995451, 0.1073969566],
    [0.0883024619, 0.2817188376, 0.6299787005],
];

const M2: [[f32; 3]; 3] = [
    [0.2104542553, 0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050, 0.4505937099],
    [0.0259040371, 0.7827717662, -0.8086757660],
];

const M1_INV: [[f32; 3]; 3] = [
    [4.0767416621, -3.3077115913, 0.2309699292],
    [-1.2684380046, 2.6097574011, -0.3413193965],
    [-0.0041960863, -0.7034186147, 1.7076147010],
];

const M2_INV: [[f32; 3]; 3] = [
    [1.0, 0.3963377774, 0.2158037573],
    [1.0, -0.1055613458, -0.0638541728],
    [1.0, -0.0894841775, -1.2914855480],
];

fn srgb_to_oklab(data: ArrayView2<f32>) -> Array2<f32> {
    let linear = srgb_to_linear(data);
    let rows = linear.nrows();
    let mut result = Array2::zeros((rows, 3));

    for i in 0..rows {
        let r = linear[[i, 0]];
        let g = linear[[i, 1]];
        let b = linear[[i, 2]];

        // Linear RGB to LMS
        let l = M1[0][0] * r + M1[0][1] * g + M1[0][2] * b;
        let m = M1[1][0] * r + M1[1][1] * g + M1[1][2] * b;
        let s = M1[2][0] * r + M1[2][1] * g + M1[2][2] * b;

        // Cube root
        let l_ = l.cbrt();
        let m_ = m.cbrt();
        let s_ = s.cbrt();

        // LMS to Oklab
        result[[i, 0]] = M2[0][0] * l_ + M2[0][1] * m_ + M2[0][2] * s_;
        result[[i, 1]] = M2[1][0] * l_ + M2[1][1] * m_ + M2[1][2] * s_;
        result[[i, 2]] = M2[2][0] * l_ + M2[2][1] * m_ + M2[2][2] * s_;
    }

    result
}

fn oklab_to_srgb(data: ArrayView2<f32>) -> Array2<f32> {
    let rows = data.nrows();
    let mut linear = Array2::zeros((rows, 3));

    for i in 0..rows {
        let l = data[[i, 0]];
        let a = data[[i, 1]];
        let b = data[[i, 2]];

        // Oklab to LMS (cube root space)
        let l_ = M2_INV[0][0] * l + M2_INV[0][1] * a + M2_INV[0][2] * b;
        let m_ = M2_INV[1][0] * l + M2_INV[1][1] * a + M2_INV[1][2] * b;
        let s_ = M2_INV[2][0] * l + M2_INV[2][1] * a + M2_INV[2][2] * b;

        // Cube
        let l_cubed = l_ * l_ * l_;
        let m_cubed = m_ * m_ * m_;
        let s_cubed = s_ * s_ * s_;

        // LMS to linear RGB
        linear[[i, 0]] = M1_INV[0][0] * l_cubed + M1_INV[0][1] * m_cubed + M1_INV[0][2] * s_cubed;
        linear[[i, 1]] = M1_INV[1][0] * l_cubed + M1_INV[1][1] * m_cubed + M1_INV[1][2] * s_cubed;
        linear[[i, 2]] = M1_INV[2][0] * l_cubed + M1_INV[2][1] * m_cubed + M1_INV[2][2] * s_cubed;
    }

    linear_to_srgb(linear.view())
}

fn srgb_to_oklch(data: ArrayView2<f32>) -> Array2<f32> {
    let oklab = srgb_to_oklab(data);
    oklab_to_oklch(oklab.view())
}

fn oklch_to_srgb(data: ArrayView2<f32>) -> Array2<f32> {
    let oklab = oklch_to_oklab(data);
    oklab_to_srgb(oklab.view())
}

fn oklab_to_oklch(data: ArrayView2<f32>) -> Array2<f32> {
    let rows = data.nrows();
    let mut result = Array2::zeros((rows, 3));

    for i in 0..rows {
        let l = data[[i, 0]];
        let a = data[[i, 1]];
        let b = data[[i, 2]];

        let c = (a * a + b * b).sqrt();
        let h = if c < 1e-10 {
            0.0
        } else {
            let h_rad = b.atan2(a);
            let h_norm = h_rad / (2.0 * PI);
            if h_norm < 0.0 {
                h_norm + 1.0
            } else {
                h_norm
            }
        };

        result[[i, 0]] = l;
        result[[i, 1]] = c;
        result[[i, 2]] = h;
    }

    result
}

fn oklch_to_oklab(data: ArrayView2<f32>) -> Array2<f32> {
    let rows = data.nrows();
    let mut result = Array2::zeros((rows, 3));

    for i in 0..rows {
        let l = data[[i, 0]];
        let c = data[[i, 1]];
        let h = data[[i, 2]];

        let h_rad = h * 2.0 * PI;
        let a = c * h_rad.cos();
        let b = c * h_rad.sin();

        result[[i, 0]] = l;
        result[[i, 1]] = a;
        result[[i, 2]] = b;
    }

    result
}

// OkHSL/OkHSV conversions (simplified approximation)
fn srgb_to_okhsl(data: ArrayView2<f32>) -> Array2<f32> {
    let oklab = srgb_to_oklab(data);
    let rows = oklab.nrows();
    let mut result = Array2::zeros((rows, 3));

    for i in 0..rows {
        let l = oklab[[i, 0]];
        let a = oklab[[i, 1]];
        let b = oklab[[i, 2]];

        let c = (a * a + b * b).sqrt();
        let h = if c < 1e-10 {
            0.0
        } else {
            let h_rad = b.atan2(a);
            let h_norm = h_rad / (2.0 * PI);
            if h_norm < 0.0 {
                h_norm + 1.0
            } else {
                h_norm
            }
        };

        // Approximate saturation
        let s = if l < 1e-10 || l > 1.0 - 1e-10 {
            0.0
        } else {
            c / (l.min(1.0 - l) * 2.0).max(0.001)
        };

        result[[i, 0]] = h;
        result[[i, 1]] = s.clamp(0.0, 1.0);
        result[[i, 2]] = l;
    }

    result
}

fn okhsl_to_srgb(data: ArrayView2<f32>) -> Array2<f32> {
    let rows = data.nrows();
    let mut oklab = Array2::zeros((rows, 3));

    for i in 0..rows {
        let h = data[[i, 0]];
        let s = data[[i, 1]];
        let l = data[[i, 2]];

        // Approximate chroma from saturation
        let c = s * l.min(1.0 - l) * 2.0;

        let h_rad = h * 2.0 * PI;
        let a = c * h_rad.cos();
        let b = c * h_rad.sin();

        oklab[[i, 0]] = l;
        oklab[[i, 1]] = a;
        oklab[[i, 2]] = b;
    }

    oklab_to_srgb(oklab.view())
}

fn srgb_to_okhsv(data: ArrayView2<f32>) -> Array2<f32> {
    let oklab = srgb_to_oklab(data);
    let rows = oklab.nrows();
    let mut result = Array2::zeros((rows, 3));

    for i in 0..rows {
        let l = oklab[[i, 0]];
        let a = oklab[[i, 1]];
        let b = oklab[[i, 2]];

        let c = (a * a + b * b).sqrt();
        let h = if c < 1e-10 {
            0.0
        } else {
            let h_rad = b.atan2(a);
            let h_norm = h_rad / (2.0 * PI);
            if h_norm < 0.0 {
                h_norm + 1.0
            } else {
                h_norm
            }
        };

        // Approximate V and S for HSV
        let v = l + c;
        let s = if v < 1e-10 { 0.0 } else { 2.0 * c / v };

        result[[i, 0]] = h;
        result[[i, 1]] = s.clamp(0.0, 1.0);
        result[[i, 2]] = v.clamp(0.0, 1.0);
    }

    result
}

fn okhsv_to_srgb(data: ArrayView2<f32>) -> Array2<f32> {
    let rows = data.nrows();
    let mut oklab = Array2::zeros((rows, 3));

    for i in 0..rows {
        let h = data[[i, 0]];
        let s = data[[i, 1]];
        let v = data[[i, 2]];

        let c = v * s / 2.0;
        let l = v - c;

        let h_rad = h * 2.0 * PI;
        let a = c * h_rad.cos();
        let b = c * h_rad.sin();

        oklab[[i, 0]] = l;
        oklab[[i, 1]] = a;
        oklab[[i, 2]] = b;
    }

    oklab_to_srgb(oklab.view())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_color_model_from_str() {
        assert_eq!(ColorModel::from_str("rgb"), Some(ColorModel::Srgb));
        assert_eq!(ColorModel::from_str("srgb"), Some(ColorModel::Srgb));
        assert_eq!(ColorModel::from_str("hsl"), Some(ColorModel::Hsl));
        assert_eq!(ColorModel::from_str("oklch"), Some(ColorModel::Oklch));
    }

    #[test]
    fn test_srgb_roundtrip_hsl() {
        let data = Array2::from_shape_vec((1, 3), vec![1.0, 0.0, 0.0]).unwrap();
        let hsl = srgb_to_hsl(data.view());
        let back = hsl_to_srgb(hsl.view());
        assert!((back[[0, 0]] - 1.0).abs() < 0.01);
        assert!((back[[0, 1]] - 0.0).abs() < 0.01);
        assert!((back[[0, 2]] - 0.0).abs() < 0.01);
    }

    #[test]
    fn test_srgb_roundtrip_oklab() {
        let data = Array2::from_shape_vec((1, 3), vec![0.5, 0.5, 0.5]).unwrap();
        let oklab = srgb_to_oklab(data.view());
        let back = oklab_to_srgb(oklab.view());
        assert!((back[[0, 0]] - 0.5).abs() < 0.01);
        assert!((back[[0, 1]] - 0.5).abs() < 0.01);
        assert!((back[[0, 2]] - 0.5).abs() < 0.01);
    }
}
