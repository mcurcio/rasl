# @rasl/config

Configuration file parsing for RASL `.conf` files.

## Overview

This package provides a parser for RASL configuration files, which use a custom DSL for defining node graphs. The parser produces both a Concrete Syntax Tree (CST) for lossless source representation and an Abstract Syntax Tree (AST) for semantic processing.

## Key Types

### CST (Concrete Syntax Tree)

- `ICstNode` - Base interface for all CST nodes
- `ICstDocument` - Root document node
- `ICstNodeBlock` - Node definition block
- `ICstConnection` - Connection between nodes
- `ICstProperty` - Property assignment

### AST (Abstract Syntax Tree)

- `IAstDocument` - Parsed document with nodes and connections
- `IAstNodeDef` - Node definition with type and properties
- `IAstConnection` - Resolved connection between ports
- `IAstProperty` - Typed property value

### Parser

- `parse(source: string): IParseResult` - Parse a config file
- `IParseResult` - Contains CST, AST, and any diagnostics

## Example Config

```nginx
node Waveform sine {
    shape sine;
    frequency_hz 0.5;
    output_channels 512;
}

node ConsoleSink console {
    fps 30;
    connect sine;
}
```

## Usage

```typescript
import { parse } from '@rasl/config';

const result = parse(configSource);
if (result.errors.length === 0) {
  console.log('Nodes:', result.ast.nodes);
  console.log('Connections:', result.ast.connections);
}
```
