//! Payload types for frame data.
//!
//! Payloads are the data containers that flow through the graph.
//! The base type is [`MatrixPayload`] which holds 2D numeric data.

use ndarray::{Array2, ArrayView2};
use std::fmt;

/// Trait for all payload types that can flow through the graph.
pub trait Payload: Clone + Send + Sync + 'static {
    /// Number of elements (rows) in the payload.
    fn count(&self) -> usize;

    /// Number of channels (columns) per element.
    fn channels(&self) -> usize;

    /// Total number of values (count * channels).
    fn size(&self) -> usize {
        self.count() * self.channels()
    }

    /// Get the underlying data as a 2D array view.
    fn as_array(&self) -> ArrayView2<f32>;

    /// Domain identifier for type checking.
    fn domain(&self) -> &'static str;
}

/// Base payload type for numeric signal data.
///
/// MatrixPayload represents a 2D numeric matrix with shape (count, channels).
/// This is the universal currency for signal data in RASL.
///
/// Shape convention:
/// - count: First dimension (number of elements, e.g., number of pixels)
/// - channels: Second dimension (dimensions per element, e.g., 3 for RGB)
#[derive(Clone)]
pub struct MatrixPayload {
    data: Array2<f32>,
}

impl MatrixPayload {
    /// Create a new MatrixPayload from a 2D array.
    pub fn new(data: Array2<f32>) -> Self {
        Self { data }
    }

    /// Create a new MatrixPayload from a 1D slice, reshaping to (n, 1).
    pub fn from_slice(data: &[f32]) -> Self {
        let arr = Array2::from_shape_vec((data.len(), 1), data.to_vec())
            .expect("slice to array conversion should not fail");
        Self { data: arr }
    }

    /// Create a new MatrixPayload from nested vectors.
    pub fn from_vec2(data: Vec<Vec<f32>>) -> Self {
        if data.is_empty() {
            return Self {
                data: Array2::zeros((0, 0)),
            };
        }
        let rows = data.len();
        let cols = data[0].len();
        let flat: Vec<f32> = data.into_iter().flatten().collect();
        let arr = Array2::from_shape_vec((rows, cols), flat)
            .expect("vec2 to array conversion should not fail");
        Self { data: arr }
    }

    /// Create a payload filled with a constant value.
    pub fn filled(count: usize, channels: usize, value: f32) -> Self {
        Self {
            data: Array2::from_elem((count, channels), value),
        }
    }

    /// Create a payload filled with zeros.
    pub fn zeros(count: usize, channels: usize) -> Self {
        Self::filled(count, channels, 0.0)
    }

    /// Get mutable access to the underlying array.
    pub fn as_array_mut(&mut self) -> &mut Array2<f32> {
        &mut self.data
    }

    /// Consume and return the underlying array.
    pub fn into_array(self) -> Array2<f32> {
        self.data
    }

    /// Repeat the payload n times along the row axis.
    pub fn repeat(&self, n: usize) -> Self {
        if n <= 1 {
            return self.clone();
        }
        let (rows, cols) = self.data.dim();
        let new_rows = rows * n;
        let mut new_data = Array2::zeros((new_rows, cols));
        for i in 0..n {
            new_data
                .slice_mut(ndarray::s![i * rows..(i + 1) * rows, ..])
                .assign(&self.data);
        }
        Self { data: new_data }
    }

    /// Flatten to a 1D vector.
    pub fn flatten(&self) -> Vec<f32> {
        self.data.iter().copied().collect()
    }

    /// Truncate to the first n rows.
    pub fn truncate(&self, n: usize) -> Self {
        let (rows, cols) = self.data.dim();
        if n >= rows {
            return self.clone();
        }
        let truncated = self.data.slice(ndarray::s![..n, ..]).to_owned();
        Self { data: truncated }
    }

    /// Get a single row as a vector.
    pub fn row(&self, index: usize) -> Option<Vec<f32>> {
        if index < self.count() {
            Some(self.data.row(index).to_vec())
        } else {
            None
        }
    }
}

impl Payload for MatrixPayload {
    fn count(&self) -> usize {
        self.data.nrows()
    }

    fn channels(&self) -> usize {
        self.data.ncols()
    }

    fn as_array(&self) -> ArrayView2<f32> {
        self.data.view()
    }

    fn domain(&self) -> &'static str {
        "matrix"
    }
}

impl fmt::Debug for MatrixPayload {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let (rows, cols) = self.data.dim();
        write!(f, "MatrixPayload<{}x{}>", rows, cols)
    }
}

impl fmt::Display for MatrixPayload {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let (rows, _cols) = self.data.dim();
        let max_rows = 5;
        let shown = rows.min(max_rows);

        write!(f, "[")?;
        for i in 0..shown {
            if i > 0 {
                write!(f, ", ")?;
            }
            let row: Vec<String> = self
                .data
                .row(i)
                .iter()
                .map(|v| format!("{:.3}", v))
                .collect();
            write!(f, "[{}]", row.join(", "))?;
        }
        if rows > max_rows {
            write!(f, ", ...")?;
        }
        write!(f, "]")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_matrix_payload_from_slice() {
        let payload = MatrixPayload::from_slice(&[1.0, 2.0, 3.0]);
        assert_eq!(payload.count(), 3);
        assert_eq!(payload.channels(), 1);
    }

    #[test]
    fn test_matrix_payload_from_vec2() {
        let payload = MatrixPayload::from_vec2(vec![
            vec![1.0, 0.0, 0.0],
            vec![0.0, 1.0, 0.0],
            vec![0.0, 0.0, 1.0],
        ]);
        assert_eq!(payload.count(), 3);
        assert_eq!(payload.channels(), 3);
    }

    #[test]
    fn test_matrix_payload_repeat() {
        let payload = MatrixPayload::from_vec2(vec![vec![1.0, 2.0]]);
        let repeated = payload.repeat(3);
        assert_eq!(repeated.count(), 3);
        assert_eq!(repeated.channels(), 2);
    }
}
