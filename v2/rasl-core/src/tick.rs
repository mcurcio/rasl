//! Tick context - timing information for node execution.
//!
//! The scheduler provides a TickContext to nodes during pull(),
//! containing authoritative timing information.

/// Timing context provided to nodes during execution.
///
/// The scheduler is the single time authority. Nodes should use
/// tick.t for all time-based calculations, not wall clock time.
#[derive(Debug, Clone, Copy)]
pub struct TickContext {
    /// Tick number (monotonically increasing).
    pub tick: u64,

    /// Time in seconds since scheduler start.
    pub t: f64,

    /// Delta time since last tick (seconds).
    pub dt: f64,

    /// Wall clock time (for timestamps, not animation).
    pub wall_time: f64,
}

impl TickContext {
    /// Create a new tick context.
    pub fn new(tick: u64, t: f64, dt: f64, wall_time: f64) -> Self {
        Self {
            tick,
            t,
            dt,
            wall_time,
        }
    }

    /// Create the first tick (tick 0).
    pub fn first(wall_time: f64) -> Self {
        Self {
            tick: 0,
            t: 0.0,
            dt: 0.0,
            wall_time,
        }
    }

    /// Create the next tick.
    pub fn next(&self, dt: f64, wall_time: f64) -> Self {
        Self {
            tick: self.tick + 1,
            t: self.t + dt,
            dt,
            wall_time,
        }
    }
}

impl Default for TickContext {
    fn default() -> Self {
        Self::first(0.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tick_context_next() {
        let tick0 = TickContext::first(1000.0);
        assert_eq!(tick0.tick, 0);
        assert_eq!(tick0.t, 0.0);

        let tick1 = tick0.next(0.033, 1000.033);
        assert_eq!(tick1.tick, 1);
        assert!((tick1.t - 0.033).abs() < 1e-10);
    }
}
