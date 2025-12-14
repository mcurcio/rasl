//! Configuration loader - builds execution plans from parsed config.

use crate::parser::{parse_config, ConfigValue, Directive, ParseError};
use rasl_core::color::ColorModel;
use rasl_core::graph::{Edge, ExecutionPlan, GraphBuilder, GraphError};
use rasl_core::node::Node;
use rasl_nodes::sinks::{ConsoleSinkConfig, ConsoleSinkNode, DdpSinkConfig, DdpSinkNode};
use rasl_nodes::sources::{LiteralConfig, LiteralNode, PayloadKind, WaveformConfig, WaveformNode, SacnSourceConfig, SacnSourceNode};
use rasl_nodes::sources::waveform::WaveShape;
use rasl_nodes::transforms::{ColorConfig, ColorNode, ComposeConfig, ComposeNode, TwinkleEffectConfig, TwinkleEffectNode, TwinkleMode};
use std::collections::HashMap;
use std::fs;
use std::path::Path;
use thiserror::Error;
use tracing::info;

/// Loader errors.
#[derive(Debug, Error)]
pub enum LoadError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Parse error: {0}")]
    Parse(#[from] ParseError),

    #[error("Graph error: {0}")]
    Graph(#[from] GraphError),

    #[error("Unknown node type: {0}")]
    UnknownNodeType(String),

    #[error("Invalid configuration for node '{0}': {1}")]
    InvalidConfig(String, String),
}

/// Load configuration from a file path.
pub fn load_config(path: impl AsRef<Path>) -> Result<ExecutionPlan, LoadError> {
    let content = fs::read_to_string(path.as_ref())?;
    build_plan(&content)
}

/// Connection info with modifiers.
struct ConnectionInfo {
    source: String,
    source_port: String,
    target: String,
    target_port: String,
    repeat: Option<usize>,
    repeat_until: Option<usize>,
}

/// Build an execution plan from configuration text.
pub fn build_plan(config_text: &str) -> Result<ExecutionPlan, LoadError> {
    let rasl = parse_config(config_text)?;
    let mut builder = GraphBuilder::new();
    let mut connections: Vec<ConnectionInfo> = Vec::new();

    // First pass: create all nodes
    for directive in &rasl.block {
        if directive.keyword != "node" {
            continue;
        }

        let (node, node_connections) = build_node(directive)?;
        let node_id = node.id().to_string();
        builder.add_node(node)?;
        
        // Collect connections for second pass
        for conn in node_connections {
            connections.push(ConnectionInfo {
                source: conn.source,
                source_port: conn.source_port,
                target: node_id.clone(),
                target_port: conn.target_port,
                repeat: conn.repeat,
                repeat_until: conn.repeat_until,
            });
        }
    }

    // Second pass: add edges
    for conn in connections {
        let mut edge = Edge::new(&conn.source, &conn.source_port, &conn.target, &conn.target_port);
        if let Some(n) = conn.repeat {
            edge = edge.with_repeat(n);
        }
        if let Some(n) = conn.repeat_until {
            edge = edge.with_repeat_until(n);
        }
        builder.add_edge(edge)?;
    }

    let plan = builder.build()?;
    info!(
        nodes = plan.nodes.len(),
        rate_drivers = plan.rate_drivers.len(),
        "config_loaded"
    );

    Ok(plan)
}

/// Parsed connection from config.
struct ParsedConnection {
    source: String,
    source_port: String,
    target_port: String,
    repeat: Option<usize>,
    repeat_until: Option<usize>,
}

/// Build a node from a directive.
/// Returns the node and a list of connections.
fn build_node(directive: &Directive) -> Result<(Box<dyn Node>, Vec<ParsedConnection>), LoadError> {
    let node_type = directive.get_arg(0).ok_or_else(|| {
        LoadError::InvalidConfig("unknown".to_string(), "missing node type".to_string())
    })?;

    let node_id = directive.get_arg(1).ok_or_else(|| {
        LoadError::InvalidConfig(node_type.to_string(), "missing node id".to_string())
    })?;

    let config = directive.to_config();
    let mut connections = Vec::new();

    // Parse connect directives
    for child in &directive.block {
        if child.keyword == "connect" {
            let source = match child.get_arg(0) {
                Some(s) => s.to_string(),
                None => continue,
            };
            
            let target_port = child.get_arg(1)
                .map(|s| s.to_string())
                .unwrap_or_else(|| get_default_input_port(node_type));
            
            // Parse modifiers from child block
            let mut repeat = None;
            let mut repeat_until = None;
            
            for modifier in &child.block {
                match modifier.keyword.as_str() {
                    "repeat" => {
                        if let Some(n) = modifier.get_int(0) {
                            repeat = Some(n as usize);
                        }
                    }
                    "repeat_until" => {
                        if let Some(n) = modifier.get_int(0) {
                            repeat_until = Some(n as usize);
                        }
                    }
                    _ => {}
                }
            }
            
            connections.push(ParsedConnection {
                source,
                source_port: "out".to_string(),
                target_port,
                repeat,
                repeat_until,
            });
        }
    }

    let node: Box<dyn Node> = match node_type.to_lowercase().as_str() {
        "waveform" | "waveformnode" => {
            let mut wc = WaveformConfig {
                id: node_id.to_string(),
                ..Default::default()
            };

            if let Some(v) = config.get("shape").and_then(|v| v.as_str()) {
                wc.shape = WaveShape::from_str(v).unwrap_or_default();
            }
            if let Some(v) = config.get("frequency_hz").and_then(|v| v.as_float()) {
                wc.frequency_hz = v;
            }
            if let Some(v) = config.get("output_channels").and_then(|v| v.as_int()) {
                wc.output_channels = v as usize;
            }
            if let Some(v) = config.get("attack_ratio").and_then(|v| v.as_float()) {
                wc.attack_ratio = v as f32;
            }
            if let Some(v) = config.get("duty").and_then(|v| v.as_float()) {
                wc.duty = v as f32;
            }

            Box::new(WaveformNode::new(wc))
        }

        "literal" | "literalnode" => {
            // node literal <name> <kind:subtype> <value>
            let type_spec = directive.get_arg(2).unwrap_or("matrix");
            let value_str = directive.args.get(3..).map(|a| a.join(" ")).unwrap_or_default();

            let (kind, subtype) = if type_spec.contains(':') {
                let parts: Vec<&str> = type_spec.split(':').collect();
                (parts[0], Some(parts[1]))
            } else {
                (type_spec, None)
            };

            let payload_kind = PayloadKind::from_str(kind).unwrap_or(PayloadKind::Matrix);
            let color_model = subtype.and_then(ColorModel::from_str);

            // Parse the literal value
            let data = parse_literal_value(&value_str)?;

            Box::new(LiteralNode::new(LiteralConfig {
                id: node_id.to_string(),
                kind: payload_kind,
                color_model,
                data,
            }))
        }

        "compose" | "composenode" => {
            let mut cc = ComposeConfig {
                id: node_id.to_string(),
                ..Default::default()
            };

            // Parse ports block
            if let Some(ports_dir) = directive.find("ports") {
                cc.ports = ports_dir.block.iter().map(|d| d.keyword.clone()).collect();
            }

            // Parse fill directives
            for child in &directive.block {
                if child.keyword == "fill" {
                    if let (Some(port), Some(value)) = (child.get_arg(0), child.get_float(1)) {
                        cc.fill.insert(port.to_string(), value as f32);
                    }
                }
            }

            // Parse output_type
            if let Some(v) = config.get("output_type").and_then(|v| v.as_str()) {
                cc.output_type = v.to_string();
            }

            if let Some(v) = config.get("output_channels").and_then(|v| v.as_int()) {
                cc.output_channels = Some(v as usize);
            }

            Box::new(ComposeNode::new(cc))
        }

        "color" | "colornode" => {
            let model_str = directive.get_arg(2).unwrap_or("srgb");
            let model = ColorModel::from_str(model_str).unwrap_or(ColorModel::Srgb);

            Box::new(ColorNode::new(ColorConfig {
                id: node_id.to_string(),
                model,
            }))
        }

        "consolesink" | "consolesinknode" => {
            let mut cc = ConsoleSinkConfig {
                id: node_id.to_string(),
                ..Default::default()
            };

            if let Some(v) = config.get("max_channels").and_then(|v| v.as_int()) {
                cc.max_channels = v as usize;
            }
            if let Some(v) = config.get("fps").and_then(|v| v.as_float()) {
                cc.fps = v;
            }
            if let Some(v) = config.get("as_bytes").and_then(|v| v.as_bool()) {
                cc.as_bytes = v;
            }
            if let Some(v) = config.get("include_metadata").and_then(|v| v.as_bool()) {
                cc.include_metadata = v;
            }
            if let Some(v) = config.get("input_port").and_then(|v| v.as_str()) {
                cc.input_port = v.to_string();
            }
            if let Some(v) = config.get("label").and_then(|v| v.as_str()) {
                cc.label = Some(v.to_string());
            }

            Box::new(ConsoleSinkNode::new(cc))
        }

        "twinkleeffect" | "twinkleeffectnode" => {
            let mut tc = TwinkleEffectConfig {
                id: node_id.to_string(),
                ..Default::default()
            };

            if let Some(v) = config.get("seed").and_then(|v| v.as_int()) {
                tc.seed = v as u64;
            }
            if let Some(v) = config.get("mode").and_then(|v| v.as_str()) {
                tc.mode = TwinkleMode::from_str(v).unwrap_or(TwinkleMode::Brightness);
            }
            if let Some(v) = config.get("frequency_hz").and_then(|v| v.as_float()) {
                tc.frequency_hz = v as f32;
            }
            if let Some(v) = config.get("attack_ratio").and_then(|v| v.as_float()) {
                tc.attack_ratio = v as f32;
            }
            if let Some(v) = config.get("min_speed").and_then(|v| v.as_float()) {
                tc.min_speed = v as f32;
            }
            if let Some(v) = config.get("max_speed").and_then(|v| v.as_float()) {
                tc.max_speed = v as f32;
            }

            Box::new(TwinkleEffectNode::new(tc))
        }

        "ddpsink" | "ddpsinknode" => {
            let mut dc = DdpSinkConfig {
                id: node_id.to_string(),
                ..Default::default()
            };

            if let Some(v) = config.get("target").and_then(|v| v.as_str()) {
                dc.target = v.to_string();
            }
            if let Some(v) = config.get("fps").and_then(|v| v.as_str()) {
                if let Some(fps) = DdpSinkNode::parse_fps(v) {
                    dc.fps = fps;
                }
            } else if let Some(v) = config.get("fps").and_then(|v| v.as_float()) {
                dc.fps = v;
            }
            if let Some(v) = config.get("input_port").and_then(|v| v.as_str()) {
                dc.input_port = v.to_string();
            }
            if let Some(v) = config.get("max_count").and_then(|v| v.as_int()) {
                dc.max_count = Some(v as usize);
            }

            Box::new(DdpSinkNode::new(dc))
        }

        "sacnsource" | "sacnsourcenode" => {
            let mut sc = SacnSourceConfig {
                id: node_id.to_string(),
                ..Default::default()
            };

            if let Some(v) = config.get("universes").and_then(|v| v.as_int()) {
                sc.universes = vec![v as u16];
            }
            if let Some(v) = config.get("bind_address").and_then(|v| v.as_str()) {
                sc.bind_address = v.to_string();
            }
            if let Some(v) = config.get("bind_port").and_then(|v| v.as_int()) {
                sc.bind_port = v as u16;
            }

            Box::new(SacnSourceNode::new(sc))
        }

        _ => {
            return Err(LoadError::UnknownNodeType(node_type.to_string()));
        }
    };

    Ok((node, connections))
}

/// Get the default input port name for a node type.
fn get_default_input_port(node_type: &str) -> String {
    match node_type.to_lowercase().as_str() {
        "color" | "colornode" => "color".to_string(),
        "consolesink" | "consolesinknode" => "dmx".to_string(),
        "twinkleeffect" | "twinkleeffectnode" => "input".to_string(),
        "ddpsink" | "ddpsinknode" => "pixels".to_string(),
        _ => "in".to_string(),
    }
}

/// Parse a literal value string into nested vectors.
fn parse_literal_value(value: &str) -> Result<Vec<Vec<f32>>, LoadError> {
    let trimmed = value.trim();
    
    if trimmed.is_empty() {
        return Ok(Vec::new());
    }

    // Simple parser for [[a, b, c], [d, e, f]] format
    if !trimmed.starts_with('[') {
        return Err(LoadError::InvalidConfig(
            "literal".to_string(),
            format!("expected array literal, got: {}", trimmed),
        ));
    }

    // Remove outer brackets - find matching bracket
    let inner = &trimmed[1..trimmed.len()-1].trim();

    if inner.is_empty() {
        return Ok(Vec::new());
    }

    // Check if it's a nested array
    if inner.starts_with('[') {
        // Parse nested arrays
        let mut result = Vec::new();
        let mut depth = 0;
        let mut start = 0;

        for (i, c) in inner.char_indices() {
            match c {
                '[' => {
                    if depth == 0 {
                        start = i + 1;
                    }
                    depth += 1;
                }
                ']' => {
                    depth -= 1;
                    if depth == 0 {
                        // Parse the row between start and i
                        let row_str = &inner[start..i];
                        let row: Vec<f32> = row_str
                            .split(',')
                            .filter_map(|s| s.trim().parse().ok())
                            .collect();
                        if !row.is_empty() {
                            result.push(row);
                        }
                    }
                }
                _ => {}
            }
        }

        Ok(result)
    } else {
        // Single row
        let row: Vec<f32> = inner
            .split(',')
            .filter_map(|s| s.trim().parse().ok())
            .collect();
        Ok(vec![row])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_literal_value_nested() {
        let result = parse_literal_value("[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]").unwrap();
        assert_eq!(result.len(), 2);
        assert_eq!(result[0], vec![1.0, 0.0, 0.0]);
        assert_eq!(result[1], vec![0.0, 1.0, 0.0]);
    }

    #[test]
    fn test_parse_literal_value_single() {
        let result = parse_literal_value("[1.0, 2.0, 3.0]").unwrap();
        assert_eq!(result.len(), 1);
        assert_eq!(result[0], vec![1.0, 2.0, 3.0]);
    }

    #[test]
    fn test_build_simple_graph() {
        let config = r#"
            rasl {
                node Waveform source {
                    shape sawtooth;
                    frequency_hz 0.1;
                    output_channels 3;
                }
                node ConsoleSink sink {
                    fps 1;
                    connect source;
                }
            }
        "#;

        let plan = build_plan(config).unwrap();
        assert_eq!(plan.nodes.len(), 2);
        assert!(plan.rate_drivers.contains_key("sink"));
    }

    #[test]
    fn test_build_color_pipeline() {
        let config = r#"
            rasl {
                node literal colors color:hsl [[0.0, 1.0, 0.5]];
                node Color toRgb rgb {
                    connect colors;
                }
                node ConsoleSink sink {
                    fps 1;
                    connect toRgb color;
                }
            }
        "#;

        let plan = build_plan(config).unwrap();
        assert_eq!(plan.nodes.len(), 3);
    }
}
