# DAG and Connection Configuration Design

This document specifies how RASL builds a graph of node ports from NGINX-style configuration files, with a focus on the `connect` directive syntax for channel-level routing.

The config is parsed by **crossplane** into directives + args. This document defines the **second-stage semantics**: how `connect` directives are interpreted and validated to build the execution graph.

---

## 1. Core Concepts

- **Nodes**  
  Logical units in the graph, each with input and/or output ports.

- **Ports**  
  Typed connection points on a node. Ports are directional:
  - **Input ports** consume frames.
  - **Output ports** produce frames.

- **Port groups and default ports**  
  A node may have multiple input and/or output ports. For each direction:
  - If a node has **exactly one** input port, that port is the **default input**.
  - If a node has **exactly one** output port, that port is the **default output**.
  - Nodes do **not** explicitly mark defaults; defaults are derived from port counts.

- **Graph model**  
  The execution graph is modeled at the **channel level**:
  - **Vertices**: individual port channels.
  - **Edges**: connections from source output port channels to destination input port channels.

- **Cycles**  
  The graph may contain cycles. Cycles are detected and reported as warnings at startup, but do not prevent graph execution. Node implementations are responsible for handling cyclic data flow appropriately.

---

## 2. Lexical Rules

- **Identifiers**
  - Pattern: `/[A-Za-z_][A-Za-z0-9_]*/`
  - Case-sensitive.
  - Node names are unique among all nodes.
  - Port names are unique **per direction per node**.

- **Keywords**
  - Reserved: `rasl`, `node`, `connect`, `type`, `input`, `output`, `segment`, `defaults`, `metadata`
  - Using a reserved keyword as a node or port name is a config error.

- **Comments**
  - `#` starts a comment to end-of-line.

- **Whitespace and statements**
  - Whitespace between tokens is free.
  - Directives are terminated by `;`.
  - Multiple directives per line are allowed.

---

## 3. `connect` Directive Syntax

`connect` directives define connections **into** the current node from upstream sources (pull-based semantics).

### 3.1 Grammar

```ebnf
connect_directive = "connect" source_spec [dest_spec] ";" ;

source_spec = node_ref ["." port_name] [slice] ;
dest_spec   = port_name [slice] ;

node_ref    = identifier ;
port_name   = identifier ;
slice       = "[" slice_expr "]" ;
slice_expr  = index | range ;
index       = integer ;
range       = integer ":" [integer] ;

identifier  = /[A-Za-z_][A-Za-z0-9_]*/ ;
integer     = /[0-9]+/ ;
```

### 3.2 Examples

```conf
node mixer {
    type MixerNode;
    
    # Default source port → default dest port (full mapping)
    connect upstream;
    
    # Explicit source port → default dest port
    connect upstream.intensity;
    
    # Source slice → default dest port slice
    connect upstream[0:3];
    connect upstream[5];           # single channel
    connect upstream[10:];         # open-ended
    
    # Source slice → explicit dest port slice
    connect upstream[0:3] input[0:3];
    connect upstream[0:3] input[6:9];
    
    # Explicit source port with slice → explicit dest port with slice
    connect upstream.rgb[0:3] color[0:3];
    
    # Multiple sources to non-overlapping dest ranges
    connect nodeA[0:3] input[0:3];
    connect nodeB[0:3] input[3:6];
}
```

---

## 4. Port Channel Specification

Ports declare their channel count using a unified `channels` parameter.

### 4.1 Channel Spec Format

| Format | Meaning | Example |
|--------|---------|---------|
| `int` | Fixed channel count | `channels=512` |
| `(min,)` | Variable, minimum only | `channels=(0,)` |
| `(min, max)` | Variable with bounds | `channels=(0, 512)` |
| `None` | Variable, no bounds | `channels=None` |

### 4.2 PortSpec Definition

```python
@dataclass(frozen=True, slots=True)
class PortSpec:
    accepts: PayloadType
    channels: int | tuple[int] | tuple[int, int] | None = None
    description: str = ""
    
    @property
    def is_variable(self) -> bool: ...
    
    @property
    def fixed_channels(self) -> int | None: ...
    
    @property
    def min_channels(self) -> int: ...
    
    @property
    def max_channels(self) -> int | None: ...
    
    def validate_index(self, index: int) -> bool: ...
    def validate_range(self, start: int, end: int) -> bool: ...
```

### 4.3 Examples

```python
# Fixed 512 channels
PortSpec(accepts=ArrayPayload, channels=512)

# Variable, no minimum (unbounded)
PortSpec(accepts=ArrayPayload, channels=(0,))

# Variable, at least 3 channels
PortSpec(accepts=ArrayPayload, channels=(3,))

# Variable, 0-512 channels
PortSpec(accepts=ArrayPayload, channels=(0, 512))

# Variable, no bounds (default)
PortSpec(accepts=ArrayPayload)
```

---

## 5. Slice Semantics

Slices select contiguous channel ranges on ports.

### 5.1 Allowed Forms

| Form | Meaning | Length |
|------|---------|--------|
| `[n]` | Single channel n | 1 |
| `[start:end]` | Channels [start, end) | end - start |
| `[start:]` | Channels from start to port end | Open-ended |

### 5.2 Rules

- Indices are **0-based**.
- End is **exclusive**.
- Negative indices are **not allowed**.
- Slice bounds are validated against port channel specs.

### 5.3 Length Matching

Given source slice `S` and destination slice `D`:

1. **Both explicit lengths**: `S.length == D.length` required, else **error**
2. **One open-ended**: Truncate to the shorter (no warning)
3. **Both open-ended, at least one finite port**: Use finite port's remaining length
4. **Both open-ended, both variable ports**: **Error** — cannot determine mapping length

### 5.4 Default Slice Behavior

When no slice is specified:
- If both ports have the same fixed length: map all channels
- If one port is variable: map up to the size of the finite port
- If both ports are variable with no explicit slice: **error**

---

## 6. Defaults and Name Resolution

- **Default ports**
  - If no source port is specified, the source node's **default output port** is used.
  - If no destination port is specified, the current node's **default input port** is used.
  - If a node does not have exactly one port in the required direction, using a default is a **config error**.

- **Unknown references**
  - If `sourceNode` does not match any declared node → **config error**.
  - If `sourcePort` does not exist as an **output** port on that node → **config error**.
  - If `destPort` does not exist as an **input** port on the current node → **config error**.

---

## 7. Direction, Fan-In, and Overlaps

- **Port direction**
  - The source side of a `connect` must resolve to an **output** port.
  - The destination side must resolve to an **input** port on the current node.

- **Fan-in and overlaps**
  - At most one source may drive any given destination channel.
  - Any **duplicate** or **overlapping** assignment to the same destination port/channel is a **config error**.
  - Non-overlapping ranges into the same destination port are allowed.

---

## 8. Graph Structure and Cycles

- The graph is built at the **channel level** from all `connect` directives.
- Each `connect` adds directed edges from source channels to destination channels.
- **Cycles are allowed**.

### 8.1 Cycle Handling

- Cycles are **detected** during graph analysis using Tarjan's algorithm (SCC detection).
- For each cycle:
  - Emit a **warning** listing the nodes/ports involved.
  - The graph is still built and executed.
- Node implementations are responsible for handling cycles (e.g., using previous frame's data).

### 8.2 Warning Format

```
Warning: Cycle detected in graph
  feedback → processor → mixer → feedback
  
  Nodes in cycles may receive stale data on first frame.
```

---

## 9. Validation Pipeline

Validation occurs in stages after crossplane parsing:

```
┌─────────────────┐
│  1. Parse       │  Tokenize and build ParsedConnect
└────────┬────────┘
         │
┌────────▼────────┐
│  2. Resolve     │  Resolve default ports, validate node/port existence
└────────┬────────┘
         │
┌────────▼────────┐
│  3. Slice Check │  Validate slice bounds against port specs
└────────┬────────┘
         │
┌────────▼────────┐
│  4. Length Match│  Compute mapping length, check compatibility
└────────┬────────┘
         │
┌────────▼────────┐
│  5. Overlap     │  Register channels, detect duplicates
└────────┬────────┘
         │
┌────────▼────────┐
│  6. Cycle Detect│  Find SCCs, emit warnings (do not reject)
└────────┬────────┘
         │
┌────────▼────────┐
│  7. Build Plan  │  Construct ExecutionPlan with edges
└─────────────────┘
```

---

## 10. Error Reporting

On any parse or validation error:

- Report file and line number.
- Show the full line of config text.
- Show a caret (`^`) under the offending character.

```text
config.conf:12:8: Overlap error
  connect nodeA[0:3] input[0:3];
         ^
  input[0] already receives from nodeB.output[5]
```

---

## 11. Parser Specification

### 11.1 Function Signature

```python
@dataclass
class ParsedConnect:
    """Result of parsing a connect directive."""
    source_node: str
    source_port: str | None  # None = use default
    source_slice: ResolvedSlice | None  # None = full port
    dest_port: str | None  # None = use default
    dest_slice: ResolvedSlice | None  # None = full port


@dataclass(frozen=True, slots=True)
class ResolvedSlice:
    """A slice resolved from config syntax."""
    start: int
    end: int | None  # None = open-ended
    
    @property
    def is_open(self) -> bool:
        return self.end is None


def parse_connect(source: str) -> ParsedConnect:
    """Parse a connect directive string.
    
    Args:
        source: The connect directive arguments (without 'connect' keyword
                and trailing semicolon).
    
    Returns:
        ParsedConnect with resolved source and destination specifications.
    
    Raises:
        ConnectParseError: If the syntax is invalid.
    """
    ...
```

### 11.2 Parser Implementation Notes

The parser should:
1. **Tokenize** the input into: identifiers, `.`, `[`, `]`, `:`, integers
2. **Parse source_spec**: `identifier` optionally followed by `.identifier` optionally followed by `[slice]`
3. **Parse dest_spec** (if present): `identifier` optionally followed by `[slice]`
4. **Validate** slice indices are non-negative integers
5. **Return** structured `ParsedConnect` or raise `ConnectParseError` with position

---

## 12. Graph Data Model

### 12.1 Channel Mapping

```python
@dataclass(frozen=True, slots=True)
class ChannelMapping:
    """Maps a contiguous range of source channels to destination channels."""
    source_node: str
    source_port: str
    source_start: int
    dest_port: str
    dest_start: int
    length: int
```

### 12.2 Edge with Mapping

```python
@dataclass(frozen=True, slots=True)
class Edge:
    """Connection between two node ports with channel mapping."""
    source: str
    source_port: str
    target: str
    target_port: str
    mapping: ChannelMapping
```

### 12.3 Overlap Detection

```python
class PortChannelRegistry:
    """Tracks channel assignments to detect overlaps."""
    
    def assign(
        self,
        dest_node: str,
        dest_port: str,
        dest_channel: int,
        source_node: str,
        source_port: str,
        source_channel: int,
    ) -> None:
        """Record a channel assignment. Raises ConfigError on overlap."""
        ...
```

---

## 13. Runtime Considerations

### 13.1 Channel Buffer Assembly

At runtime, each input port buffer is assembled from potentially multiple source mappings:

```python
def assemble_input_buffer(
    port_spec: PortSpec,
    mappings: list[ChannelMapping],
    source_buffers: dict[tuple[str, str], NDArray[np.float32]],
) -> NDArray[np.float32]:
    """Assemble an input buffer from source channel mappings."""
    ...
```

### 13.2 Unconnected Channels

Channels not covered by any mapping receive zero (default). Partial connections are valid.

---

## 14. Implementation Notes (crossplane)

- The NGINX-style config is first parsed by **crossplane** into a JSON-like AST.
- Each directive has `directive`, `line`, `args`, and optional `block` fields.
- This design describes the **second-stage** interpretation of `connect` directives.
- crossplane handles low-level syntax (tokens, `;`, `#` comments).
- All semantic rules (defaults, slices, direction, overlaps, cycles) are enforced in RASL's config loader and graph builder.
