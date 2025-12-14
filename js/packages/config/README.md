# @rasl/config

Configuration file parsing for RASL `.conf` files.

## Overview

This package provides a parser for RASL configuration files, which use a custom DSL for defining node graphs. The parser produces both a Concrete Syntax Tree (CST) for lossless source representation and an Abstract Syntax Tree (AST) for semantic processing.

## Features

- **Round-tripping** - CST preserves all whitespace and comments for lossless serialization
- **Comments** - Line comments (`//`) and block comments (`/* */`)
- **Optional semicolons** - Trailing semicolons only required between directives on same line
- **Include directive** - Import other config files with async resolution

## Syntax

### Comments

```nginx
// Line comment

/* Block comment
   can span multiple lines */

node Waveform sine {  // inline comment
    shape sine
}
```

### Semicolons

Semicolons are optional at end of line. Only required between multiple directives on same line:

```nginx
// These are equivalent:
shape sine
shape sine;

// Semicolon required here:
shape sine; frequency_hz 0.5
```

### Include Directive

```nginx
include "./common.conf"
include "./effects/rainbow.conf"

node Waveform sine {
    shape sine
}
```

## Key Types

### Tokens

- `TokenType` - Token type enumeration (keywords, literals, punctuation, trivia)
- `IToken` - Token with source location
- `isKeyword()`, `isTrivia()`, `isComment()` - Token type helpers

### CST (Concrete Syntax Tree)

- `ICstNode` - Base interface with trivia for round-tripping
- `ICstDocument` - Root document node
- `ICstNodeBlock` - Node definition block
- `ICstConnection` - Connection between nodes
- `ICstProperty` - Property assignment
- `ICstInclude` - Include directive
- `ICstTrivia`, `ICstTriviaItem` - Whitespace/comment preservation
- `serializeCst()` - Serialize CST back to source text

### AST (Abstract Syntax Tree)

- `IAstDocument` - Parsed document with nodes, connections, and includes
- `IAstNodeDef` - Node definition with type and properties
- `IAstConnection` - Resolved connection between ports
- `IAstProperty` - Typed property value
- `IAstInclude` - Resolved include with nested document

### Parser

- `parse(source, config?)` - Synchronous parse
- `parseAsync(source, config)` - Async parse with include resolution
- `IParseConfig` - Parser options including `includeResolver`
- `IParseResult` - Contains CST, AST, source, and diagnostics

## Usage

### Basic Parsing

```typescript
import { parse } from '@rasl/config';

const result = parse(configSource);
if (result.errors.length === 0) {
  console.log('Nodes:', result.ast.nodes);
  console.log('Connections:', result.ast.connections);
}
```

### With Include Resolution

```typescript
import { parseAsync } from '@rasl/config';
import { readFile } from 'fs/promises';
import { resolve, dirname } from 'path';

const result = await parseAsync(configSource, {
  basePath: '/path/to/config',
  includeResolver: async (path) => {
    const fullPath = resolve(dirname(basePath), path);
    return readFile(fullPath, 'utf-8');
  },
});
```

### Round-Tripping

```typescript
import { parse, serializeCst } from '@rasl/config';

const result = parse(configSource);
const roundTripped = serializeCst(result.cst);

// roundTripped === configSource (preserves whitespace/comments)
```

## Example Config

```nginx
// Common LED strip configuration
include "./hardware.conf"

node Waveform hue_ramp {
    shape sawtooth
    frequency_hz 0.1
    output_channels 512
}

node Compose okhsl_color {
    output_type okhsl
    connect hue_ramp hue
    fill saturation 0.8
    fill lightness 0.65
}

node Color toRgb rgb {
    connect okhsl_color
}

node DdpSink led_strip {
    host "192.168.1.100"
    fps 44
    connect toRgb
}
```
