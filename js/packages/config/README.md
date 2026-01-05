# @rasl/config

Configuration file parsing for nginx-style `.conf` files.

## Overview

This package provides a domain-agnostic parser for nginx-style configuration files. It produces a full-fidelity Concrete Syntax Tree (CST) for lossless round-tripping, plus an AST facade for convenient traversal.

## Features

- **Round-tripping** - CST preserves all whitespace and comments for lossless serialization
- **Comments** - Line comments (`//`) and block comments (`/* */`)
- **Optional semicolons** - Newlines terminate directives; semicolons are optional
- **Include resolution** - Async include expansion with a document graph (no I/O in core)
- **Write-back** - Save changes back to the original documents

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

## Key Exports

### Tokens

- `TokenType`, `IToken` - Token model with exact source text and locations
- `DiagnosticCode`, `IDiagnostic` - Structured diagnostics with stable codes
- `isTrivia()`, `isComment()`, `isTerminator()` - Token helpers

### CST (Concrete Syntax Tree)

- `ICstDocument`, `ICstDirective` - Full-fidelity CST nodes referencing token ranges
- `serializeCst()`, `serializeDirective()` - Byte-identical serialization helpers
- `getDirectiveName()`, `getDirectiveArgs()` - Extract directive name/args from token ranges

### AST facade

- `createAst()` - Wrap a CST in a convenient traversal/edit facade
- `IAstDocument`, `IAstDirective`, `IAstDirectiveList` - High-level directive access
- `walkDirectives()`, `findDirectives()` - Traversal helpers

### Parsing

- `parse(source, config)` - Async parse with include resolution to `IDocumentGraph`
- `iterateDirectives(graph)` - Include-expanded directive iteration (preserves brace scopes)
- `save(graph, writer)` - Write modified documents back

## Usage

### Basic Parsing

```typescript
import { parse } from "@rasl/config";

const graph = await parse(configSource, {
  path: "/path/to/config.conf",
  loader: async () => [],
});

console.log(
  "Errors:",
  graph.diagnostics.filter((d) => d.severity === "error"),
);
```

### With Include Resolution

```typescript
import { parse } from "@rasl/config";
import { createFsLoader } from "@rasl/config/node";

const graph = await parse(configSource, {
  path: "/path/to/config/nginx.conf",
  loader: createFsLoader(),
});
```

### Round-Tripping

```typescript
import { parse, serializeCst, save } from "@rasl/config";
import { createFsLoader, createFsWriter } from "@rasl/config/node";

const graph = await parse(configSource, {
  path: "/path/to/config.conf",
  loader: createFsLoader(),
});
const roundTripped = serializeCst(graph.root.parseResult.cst);

// roundTripped === configSource (preserves whitespace/comments)

// After mutating CSTs in any document in the graph:
await save(graph, createFsWriter());
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
