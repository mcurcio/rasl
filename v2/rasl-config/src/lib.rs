//! RASL Config - Configuration parser for nginx-style syntax.
//!
//! Parses `.conf` files and builds execution plans.

pub mod parser;
pub mod loader;

pub use loader::load_config;
pub use parser::parse_config;
