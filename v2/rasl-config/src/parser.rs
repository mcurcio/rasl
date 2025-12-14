//! Parser for nginx-style configuration syntax.
//!
//! Parses RASL configuration files into a directive tree.

use nom::{
    branch::alt,
    bytes::complete::{tag, take_until, take_while, take_while1},
    character::complete::{char, multispace0, multispace1, none_of, one_of},
    combinator::{map, opt, recognize, value},
    multi::{many0, separated_list0},
    sequence::{delimited, pair, preceded, terminated, tuple},
    IResult,
};
use std::collections::HashMap;
use thiserror::Error;

/// Parse errors.
#[derive(Debug, Error)]
pub enum ParseError {
    #[error("Parse error at position {0}: {1}")]
    Syntax(usize, String),

    #[error("No 'rasl' block found in configuration")]
    NoRaslBlock,

    #[error("Unknown node type: {0}")]
    UnknownNodeType(String),

    #[error("Invalid configuration: {0}")]
    Invalid(String),
}

/// A parsed directive from the config.
#[derive(Debug, Clone)]
pub struct Directive {
    pub keyword: String,
    pub args: Vec<String>,
    pub block: Vec<Directive>,
    pub line: usize,
}

impl Directive {
    /// Create a new directive.
    pub fn new(keyword: impl Into<String>) -> Self {
        Self {
            keyword: keyword.into(),
            args: Vec::new(),
            block: Vec::new(),
            line: 0,
        }
    }

    /// Find a child directive by keyword.
    pub fn find(&self, keyword: &str) -> Option<&Directive> {
        self.block.iter().find(|d| d.keyword == keyword)
    }

    /// Find all child directives by keyword.
    pub fn find_all(&self, keyword: &str) -> Vec<&Directive> {
        self.block.iter().filter(|d| d.keyword == keyword).collect()
    }

    /// Get a single argument value.
    pub fn get_arg(&self, index: usize) -> Option<&str> {
        self.args.get(index).map(|s| s.as_str())
    }

    /// Get argument as float.
    pub fn get_float(&self, index: usize) -> Option<f64> {
        self.args.get(index).and_then(|s| s.parse().ok())
    }

    /// Get argument as integer.
    pub fn get_int(&self, index: usize) -> Option<i64> {
        self.args.get(index).and_then(|s| s.parse().ok())
    }

    /// Get argument as bool.
    pub fn get_bool(&self, index: usize) -> Option<bool> {
        self.args.get(index).and_then(|s| match s.to_lowercase().as_str() {
            "true" | "on" | "yes" | "1" => Some(true),
            "false" | "off" | "no" | "0" => Some(false),
            _ => None,
        })
    }

    /// Extract config as key-value pairs from child directives.
    pub fn to_config(&self) -> HashMap<String, ConfigValue> {
        let mut config = HashMap::new();
        for child in &self.block {
            if child.block.is_empty() {
                // Simple directive
                if child.args.is_empty() {
                    config.insert(child.keyword.clone(), ConfigValue::Bool(true));
                } else if child.args.len() == 1 {
                    config.insert(child.keyword.clone(), ConfigValue::String(child.args[0].clone()));
                } else {
                    config.insert(
                        child.keyword.clone(),
                        ConfigValue::List(child.args.clone()),
                    );
                }
            } else {
                // Nested block
                config.insert(
                    child.keyword.clone(),
                    ConfigValue::Block(child.to_config()),
                );
            }
        }
        config
    }
}

/// Configuration value types.
#[derive(Debug, Clone)]
pub enum ConfigValue {
    String(String),
    List(Vec<String>),
    Bool(bool),
    Block(HashMap<String, ConfigValue>),
}

impl ConfigValue {
    /// Get as string.
    pub fn as_str(&self) -> Option<&str> {
        match self {
            ConfigValue::String(s) => Some(s),
            _ => None,
        }
    }

    /// Get as float.
    pub fn as_float(&self) -> Option<f64> {
        match self {
            ConfigValue::String(s) => s.parse().ok(),
            _ => None,
        }
    }

    /// Get as int.
    pub fn as_int(&self) -> Option<i64> {
        match self {
            ConfigValue::String(s) => s.parse().ok(),
            _ => None,
        }
    }

    /// Get as bool.
    pub fn as_bool(&self) -> Option<bool> {
        match self {
            ConfigValue::Bool(b) => Some(*b),
            ConfigValue::String(s) => match s.to_lowercase().as_str() {
                "true" | "on" | "yes" | "1" => Some(true),
                "false" | "off" | "no" | "0" => Some(false),
                _ => None,
            },
            _ => None,
        }
    }
}

/// Parse a complete configuration string.
pub fn parse_config(input: &str) -> Result<Directive, ParseError> {
    let (_, directives) = parse_directives(input)
        .map_err(|e| ParseError::Syntax(0, format!("{:?}", e)))?;

    // Find rasl block
    let rasl = directives
        .into_iter()
        .find(|d| d.keyword == "rasl")
        .ok_or(ParseError::NoRaslBlock)?;

    Ok(rasl)
}

// ============================================================================
// Nom parsers
// ============================================================================

fn is_word_char(c: char) -> bool {
    c.is_alphanumeric() || c == '_' || c == '-' || c == '.' || c == ':'
}

fn ws(input: &str) -> IResult<&str, ()> {
    value((), multispace0)(input)
}

fn comment(input: &str) -> IResult<&str, ()> {
    value(
        (),
        pair(char('#'), take_while(|c| c != '\n')),
    )(input)
}

fn ws_or_comment(input: &str) -> IResult<&str, ()> {
    value((), many0(alt((value((), multispace1), comment))))(input)
}

fn word(input: &str) -> IResult<&str, &str> {
    take_while1(is_word_char)(input)
}

fn quoted_string(input: &str) -> IResult<&str, String> {
    let (input, _) = char('"')(input)?;
    let (input, content) = take_while(|c| c != '"')(input)?;
    let (input, _) = char('"')(input)?;
    Ok((input, content.to_string()))
}

fn bracket_expr(input: &str) -> IResult<&str, String> {
    let (input, _) = char('[')(input)?;
    let mut depth = 1;
    let mut end_idx = 0;
    
    for (i, c) in input.char_indices() {
        match c {
            '[' => depth += 1,
            ']' => {
                depth -= 1;
                if depth == 0 {
                    end_idx = i;
                    break;
                }
            }
            _ => {}
        }
    }
    
    if depth != 0 {
        return Err(nom::Err::Error(nom::error::Error::new(input, nom::error::ErrorKind::Char)));
    }
    
    let content = &input[..end_idx];
    let remaining = &input[end_idx + 1..];
    Ok((remaining, format!("[{}]", content)))
}

fn argument(input: &str) -> IResult<&str, String> {
    alt((
        quoted_string,
        bracket_expr,
        map(word, |s: &str| s.to_string()),
    ))(input)
}

fn arguments(input: &str) -> IResult<&str, Vec<String>> {
    separated_list0(multispace1, argument)(input)
}

fn directive_block(input: &str) -> IResult<&str, Vec<Directive>> {
    delimited(
        tuple((char('{'), ws_or_comment)),
        parse_directives_inner,
        tuple((ws_or_comment, char('}'))),
    )(input)
}

fn directive(input: &str) -> IResult<&str, Directive> {
    let (input, _) = ws_or_comment(input)?;
    let (input, keyword) = word(input)?;
    let (input, _) = ws(input)?;
    let (input, args) = arguments(input)?;
    let (input, _) = ws(input)?;
    let (input, block) = opt(directive_block)(input)?;
    let (input, _) = ws(input)?;
    let (input, _) = opt(char(';'))(input)?;

    Ok((
        input,
        Directive {
            keyword: keyword.to_string(),
            args,
            block: block.unwrap_or_default(),
            line: 0,
        },
    ))
}

fn parse_directives_inner(input: &str) -> IResult<&str, Vec<Directive>> {
    many0(directive)(input)
}

fn parse_directives(input: &str) -> IResult<&str, Vec<Directive>> {
    let (input, _) = ws_or_comment(input)?;
    let (input, directives) = parse_directives_inner(input)?;
    let (input, _) = ws_or_comment(input)?;
    Ok((input, directives))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_directive() {
        let input = "rasl { node Waveform test { shape sine; } }";
        let result = parse_config(input).unwrap();
        assert_eq!(result.keyword, "rasl");
        assert_eq!(result.block.len(), 1);
    }

    #[test]
    fn test_parse_with_comments() {
        let input = r#"
            # This is a comment
            rasl {
                # Another comment
                node Waveform test {
                    shape sine;
                    frequency_hz 1.0;
                }
            }
        "#;
        let result = parse_config(input).unwrap();
        assert_eq!(result.keyword, "rasl");
    }

    #[test]
    fn test_parse_literal_with_brackets() {
        let input = r#"
            rasl {
                node literal test color:hsl [[0.0, 1.0, 0.5], [0.33, 1.0, 0.5]];
            }
        "#;
        let result = parse_config(input).unwrap();
        let node = &result.block[0];
        assert_eq!(node.keyword, "node");
        assert!(node.args.len() >= 4);
    }

    #[test]
    fn test_parse_nested_blocks() {
        let input = r#"
            rasl {
                node Compose test {
                    ports {
                        hue;
                        saturation;
                        lightness;
                    }
                    fill saturation 1.0;
                }
            }
        "#;
        let result = parse_config(input).unwrap();
        let node = &result.block[0];
        let ports = node.find("ports").unwrap();
        assert_eq!(ports.block.len(), 3);
    }
}
