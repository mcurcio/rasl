# Node settings

This page lists the settings of every built-in node type. The [README](../README.md#node-types) lists
the types, with their inputs and outputs, and [Configuration](../README.md#configuration) explains the
config file itself.

The tables come from each node's settings model (its `Config` class in `src/rasl/nodes/` or
`src/rasl/devices/`). "Required" means the config fails to load without it.

## How settings are written

Each directive in a node's block sets one setting. A repeated directive becomes a list, a bare directive
means `true`, and a nested block becomes a map. An unknown setting is an error.

```nginx
node DdpSink leds {
    target "192.168.1.50";   # a string
    fps 30;                  # a frequency
    push_every_packet;       # a bare directive: true
    connect rgb;
}
```

Three types also take values on the node's own line, after the name:

| Type | Line | Sets |
|---|---|---|
| `Color` | `node Color <id> <model>;` | `model` |
| `literal` | `node literal <id> <kind>[:<subtype>] <value>;` | `payload_kind`, `payload_subtype`, `literal_value` |
| `cron` | `node cron <id> <field> [<field> ...];` | `schedule` (1 to 5 cron fields) |

Every other type refuses values there.

Value types used below:

- **frequency**: a number (hertz), or a number with `hz` or `fps`, such as `20hz` or `30fps`.
- **duration**: a number with a unit, such as `50ms`, `2s` or `1.5min`.
- **float**, **int**, **bool**, **string**: plain values. A setting whose name ends in `_ms` or `_s`, and
  `Crossfade`'s `seconds`, takes a plain number in that unit.

### Settings every node takes

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `metadata` | map of strings | empty | Key-value metadata attached to the node's frames: `metadata { room den; zone 2; }`, or `metadata "room=den" "zone=2";`. Both forms may be used together; a key given twice is an error. |
| `max_consecutive_errors` | int, 0 or more | the `runtime` block's (10) | Disable this node after this many failed pulls in a row; 0 means never. |

Source nodes (`Waveform`, `SineSource`, `SeededRandom`, `literal`, `cron`) also accept `fps`
(a frequency from 0.1 to 1000 Hz, unset by default). Only `SineSource` uses it; the other sources run at
the rate the sinks set.

`ConsoleSink`, `DdpSink` and `GoveeLight` take `input_port`, which renames their input port.
Their defaults are `dmx`, `input` and `light`. The name matters only when a `connect` line names
the port.

### Connecting to a node with more than one input

`connect <source>;` with no port works only when the receiving node has one input. `Waveform` (`phase`,
`speed`), `Math` (`a`, `b`), `Smooth` (`input`, `reset`), `Crossfade` and `Compose` have more than one, so
name the port: `connect m input;`. Without it the config fails with `No default port`.

## Sources

### Waveform

A periodic wave per channel. The optional `phase` input offsets each channel's phase (0 to 1), and the
optional `speed` input multiplies each channel's frequency.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `output_channels` | int | `512` | Number of output channels. |
| `shape` | `sine`, `triangle`, `sawtooth`, `attack_decay`, `square` | `sine` | Wave shape. |
| `frequency_hz` | float | `1.0` | Base frequency in hertz. |
| `attack_ratio` | float | `0.33` | Fraction of the cycle spent rising, for `attack_decay`. |
| `duty` | float | `0.5` | Fraction of the cycle that is high, for `square`. |
| `topic` | string | `waveform.<id>` | Topic name on the output frames. |

```nginx
node Waveform hue { shape sawtooth; frequency_hz 0.1; output_channels 150; }
```

### SineSource

A sine wave on every channel, for testing. Unlike the other sources it runs on its own timer, at `fps`.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `fps` | frequency | 30 | Rate at which it writes frames. |
| `output_channels` | int | `512` | Number of output channels. |
| `frequency_hz` | float | `1.0` | Sine frequency in hertz. |
| `amplitude` | float | `0.5` | Wave amplitude. |
| `offset` | float | `0.5` | Value at the centre of the wave. |
| `topic` | string | unset | Topic name on the output frames. |

### SeededRandom

Fixed random values per channel, drawn once from a seed.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `seed` | int | `42` | Random seed. |
| `output_channels` | int | `512` | Number of output channels. |
| `output_type` | `phase`, `speed`, `uniform`, `binary` | `uniform` | `phase`: 0 to 1. `speed`: `min_speed` to `max_speed`. `uniform`: `min_value` to `max_value`. `binary`: 0 or 1. |
| `min_value`, `max_value` | float | `0.0`, `1.0` | Range for `uniform`. |
| `min_speed`, `max_speed` | float | `1.0`, `3.0` | Range for `speed`. |
| `density` | float | `0.1` | Probability of a 1, for `binary`. |
| `topic` | string | unset | Topic name on the output frames. |

```nginx
node SeededRandom rnd { seed 7; output_channels 3; output_type speed; min_speed 1; max_speed 2; }
```

### literal

A constant. It is written on one line: the payload kind, an optional subtype after `:`, then the value.
The kind is `color` (the subtype is a color model; default `srgb`) or `matrix`.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `payload_kind` | string | required | `color` or `matrix`. |
| `payload_subtype` | string | unset | The color model, for `color`. |
| `literal_value` | string | required | The value, as a number or a nested list. One row per element. |

```nginx
node literal red color:srgb [[1, 0, 0]];
node literal gains matrix [[1.0, 0.9, 0.8]];
```

### cron

1 while the local time matches a cron schedule, else 0. The fields are minute, hour, day of month, month
and day of week; missing trailing fields mean `*`. This type answers only to `cron`, not to its class
name.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `schedule` | string or list of strings | `*` | The cron fields, on the node's line or as one string in the block. |

```nginx
node cron night 0 22;                          # 22:00 to 22:00:59
node cron evening { schedule "0 22-23 * * *"; }
```

### SacnUniverse

One sACN (E1.31) universe, in either direction or both. It receives the universe when any of its outputs is
connected, and sends it when its `dmx` input is; with nothing connected it opens nothing.

| Output | Type | Meaning |
|---|---|---|
| `dmx` (default) | matrix, `channels` rows of 1 column | Each DMX slot / 255 (0 to 1). A packet with fewer slots leaves the rest at 0. |
| `count` | counter | Advances once per data packet accepted, identical data included. Wraps at 65536. |
| `terminated` | bool, 1 element | 1 once the source ends its stream (and no other source is live), 0 again when data arrives. |

It makes no policy of its own: grouping channels into pixels is `Reshape`, joining universes is `connect`
ranges, and what to do when a stream stops is wiring downstream (a `count` that stops advancing).

Every SacnUniverse on the same `bind_address` and `port` shares one socket. It joins the universe's multicast
group (239.255.hi.lo) and takes unicast too; universe 0 has no group and is unicast only. If the join fails (as
on a Docker bridge network) rasl logs a warning and receives unicast only. Packets rasl sent itself are dropped.
Of several sources on one universe, the one with the highest priority wins; at equal priority the first seen
holds it until it ends its stream or is silent for 2.5 s.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `universe` | int, 0 to 63999 | required | Universe number. |
| `channels` | int, 1 to 512 | `512` | Rows on the `dmx` output. |
| `bind_address` | string | `0.0.0.0` | Interface to receive on and to join multicast groups on. |
| `port` | int | `5568` | UDP port to receive on. |
| `destination` | string | unset | Send to this host by unicast; unset sends to the universe's multicast group. Required to send universe 0. |
| `min_interval_ms` | number, 0 to 800 | `25` | Milliseconds between packets sent: the node drives the graph at 1000 / `min_interval_ms` per second (40 at 0). |
| `priority` | int, 0 to 200 | `100` | sACN priority of packets sent. |
| `source_name` | string | `RASL` | sACN source name of packets sent (63 bytes at most). |
| `multicast_ttl` | int | `8` | Time to live of multicast packets sent. |
| `send_port` | int | `0` | Local UDP port to send from (0 picks one). |
| `sync_universe` | int, 0 to 63999 | `0` | Synchronization universe of packets sent; 0 for none. |

**Sending.** Once per `min_interval_ms` the node sends its input's latest frame as one packet: values row by
row, clipped to 0..1, times 255 (truncated), cut or padded to `channels` slots. Nothing is sent before the
first frame. Nodes sending on the same `bind_address` and `send_port` share one socket, under one sACN
source id (CID) per rasl. When no node sends a universe any more, three stream-terminated packets go out; a
live reload that keeps the universe sends none. Two nodes sending the same universe to the same place load
with a warning: their packets interleave.
A node wired both ways is also pulled whenever a node reading its outputs is due, and sends then too, so it
can send faster than `min_interval_ms`.

**Synchronization.** Universes sent with the same `sync_universe` change together on receivers that support
E1.31 synchronization: after each tick in which they sent data, rasl sends one synchronization packet for
that universe (to its multicast group, or to each `destination`). Give them equal rates, or whole multiples
(40 and 20 Hz); other rates rarely share a tick and load with a warning. When receiving, data that names a
synchronization universe is held until its source's synchronization packet releases it, all universes at
once; if the source has sent none in the last 2.5 s, data is delivered as it arrives. The receiver joins the
synchronization universe's multicast group the first time data names it.

A live reload restarts the node when its wiring changes, since what it opens follows its wiring.

```nginx
node SacnUniverse wall_1 { universe 10; sync_universe 99; connect pixels[0~170]; }   # sends
node SacnUniverse wall_2 { universe 11; sync_universe 99; connect pixels[170~340]; } # changes with wall_1

node SacnUniverse u1 { universe 1; channels 432; }
node SacnUniverse u2 { universe 2; channels 24; }
node Reshape pixels {                # 152 RGB pixels: 144 from universe 1, then 8 from universe 2
    components 3;
    connect u1 input[0~432];
    connect u2 input[432~456];
}
```

## Transforms

### Compose

Interleaves named inputs into one payload, such as a color. Its inputs are the names in `ports`, in order.
Every port needs a `connect` line or a `fill` value.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `ports` | block of names | required | Input port names, in interleave order: `ports { hue; saturation; lightness; }`. |
| `fill` | `<port> <value>`, repeated | none | A constant for a port that is not connected. |
| `output_type` | string | `array` | `array` for plain numbers, or a payload type such as `color:okhsl`. |
| `output_channels` | int | unset | Values per port. Required when every port uses `fill`. |

```nginx
node Compose hsl {
    ports { hue; saturation; lightness; }
    output_type color:okhsl;
    connect hue hue;
    fill saturation 1;
    fill lightness 0.5;
}
```

### Color

Converts its input to a color model, given on the node's line.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `model` | `oklch`, `oklab`, `okhsl`, `okhsv`, `hsbk`, `srgb`, `rgbw`, `rgb`, `hsl`, `linear`, `rec709`, `rec709_rgb_prime` | required | Output color model. |

```nginx
node Color rgb rgb { connect hsl; }
```

### ColorCorrection

Gamma, saturation, brightness, and per-channel scale and offset.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `gamma` | float | `2.2` | Output gamma curve. |
| `saturation` | float | `1.0` | Saturation multiplier. |
| `brightness` | float | `1.0` | Brightness multiplier. |
| `r_scale`, `g_scale`, `b_scale` | float | `1.0` | Per-channel scale. |
| `r_offset`, `g_offset`, `b_offset` | float | `0.0` | Per-channel offset. |

### Math

Element-wise arithmetic on inputs `a` and `b`. A constant can stand in for an input that is not
connected.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `operation` | `multiply`, `add`, `subtract`, `min`, `max`, `screen`, `lerp` | `multiply` | The operation. |
| `constant_a`, `constant_b` | float | unset | Value used for `a` or `b` when it is not connected. |
| `mix` | float | `0.5` | Mix factor, for `lerp`. |
| `clamp` | bool | `true` | Clamp the output to 0 to 1. |

```nginx
node Math dim { operation multiply; constant_b 0.5; connect shuffle a; }
```

### MatrixMultiply

Applies a fixed square matrix to each channel vector.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `matrix` | list of rows, repeated | required | One `matrix [ ... ];` directive per row. Rows and columns must match. |

```nginx
node MatrixMultiply swap { matrix [0, 1, 0] [1, 0, 0] [0, 0, 1]; connect rgb; }
```

### RangeMap

Rescales each component from its own `[min, max]` range to 0 to 1.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `ranges` | list of `[min, max]` pairs | required | One pair per component; max must be above min. |
| `clamp` | bool | `true` | Clamp inputs to the range before rescaling. |

```nginx
node RangeMap rm { ranges [0, 1] [0, 1] [0, 1]; connect rnd; }
```

### Reshape

Regroups a matrix's values into rows of `components`, reading and writing row by row: 510 single
channels become 170 RGB triplets with `components 3`, and 170 triplets become 510 channels with
`components 1`. Nothing is reordered. The input is `input` and the output `output`, a plain matrix of
`components` columns.

The input's total values (rows × columns) must be a multiple of `components`. When every source's rows
and width are known at load, a total that is not is refused there, on the `connect` line: 512 channels
into `components 3` fails, 510 loads. Several sources joined into the input by target slices count the
frame the input receives, gaps included. Otherwise the node fails on the frame that breaks the rule.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `components` | int, at least 1 | required | Values per output row. Changing it restarts the node. |

```nginx
node Reshape rgb { components 3; connect dmx; }
```

### RandomMap

Maps input channels to output channels at random.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `channel_count` | int | input count | Number of output channels. |
| `seed` | int | unset | Seed for a repeatable mapping. |

### Smooth

Smoothing and slew limiting over time. Its inputs are `input` and `reset`, so name the port when you
connect it.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `smooth_period` | duration | `50ms` | Response time; `0ms` turns smoothing off. |
| `slew_period` | duration | `0s` | Shortest time a full-scale change (0 to 1) may take; smaller changes take proportionally less. `0ms` turns it off. |
| `bypass_epsilon` | float | `0.0` | Reuse the previous output when the change is below this. |

```nginx
node Smooth s { smooth_period 200ms; connect dim input; }
```

### TwinkleEffect

Per-pixel twinkle over a color input.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `seed` | int | `42` | Seed for the per-pixel values. |
| `mode` | `brightness`, `whiteness` | `brightness` | Fade to black or to white. |
| `frequency_hz` | float | `0.3` | Base twinkle frequency in hertz. |
| `attack_ratio` | float | `0.33` | Fraction of the cycle spent rising. |
| `min_speed`, `max_speed` | float | `1.0`, `3.0` | Range of the per-pixel speed multiplier. |

### Crossfade

Fades between `input0` and `input1` when the `selector` changes: false shows `input0`, true shows `input1`.
The blend is done in HSL and the output is HSL.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `seconds` | float | `1.0` | Fade time in seconds. |

```nginx
node Crossfade fade {
    seconds 2;
    connect red input0;
    connect blue input1;
    connect night selector;
}
```

## Sinks

Each sink declares a pull rate: `fps`, or `min_interval_ms` for a sending `SacnUniverse`. rasl runs a sink,
and the nodes it reads from, at that rate. A node that no sink reads from never runs.

### ConsoleSink

Prints frames to the log, for testing.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `fps` | frequency | `30hz` | Rate at which it pulls and prints frames. |
| `max_channels` | int | `16` | Most channels to print. |
| `as_bytes` | bool | `true` | Print 0 to 255 instead of 0.0 to 1.0. |
| `include_metadata` | bool | `true` | Include frame metadata in the log line. |
| `label` | string | the node id | Label in the log line. |
| `input_port` | string | `dmx` | Name of the input port. |

### DdpSink

Sends pixels over DDP, for example to WLED.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `target` | string | required | IP address to send to. |
| `fps` | frequency | `20hz` | Pull rate. |
| `max_count` | int | unset | Most elements (pixels) to send. |
| `push_every_packet` | bool | `false` | Set the DDP push flag on every packet, not only the last. |
| `input_port` | string | `input` | Name of the input port. |

```nginx
graph {
    node Waveform hue { shape sawtooth; frequency_hz 0.1; output_channels 150; }
    node Compose hsl {
        ports { hue; saturation; lightness; }
        output_type color:okhsl;
        connect hue hue;
        fill saturation 1;
        fill lightness 0.5;
    }
    node Color rgb rgb { connect hsl; }
    node DdpSink leds {
        target "192.168.1.50";
        fps 30;
        connect rgb;
    }
}
```

### LifxSink

Sets LIFX bulbs over the LAN. Each row of the color input goes to one target when the counts match; a
single row goes to every target; a single target gets the first row. Any other combination drops the
frame.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `target` | string | required | Comma-separated bulb addresses: `ip`, `ip:port`, or `mac@ip:port`. |
| `fps` | frequency | `30hz` | Pull rate. |
| `duration_ms` | float | `0.0` | Fade time per command, in milliseconds (0 to 60000). |
| `rapid` | bool | `false` | Send without asking for acknowledgements. |
| `log_unresolved_interval_s` | float | `5.0` | Seconds between warnings about targets that do not resolve (at least 0.5). |

```nginx
graph {
    node literal warm color:srgb [[1, 0.6, 0.2]];
    node LifxSink bulbs {
        target "192.168.1.60,192.168.1.61";
        fps 10;
        duration_ms 100;
        connect warm;
    }
}
```

### GoveeLight

Sets a Govee light over its LAN API. At start it asks the device for its segments and channel count. Each
frame sends one color per segment; a frame whose row count differs from the segment count is dropped.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `host` | string | required | The device's IPv4 address or host name. |
| `port` | int | `4003` | The device's LAN TCP port. |
| `fps` | frequency | `20hz` | Pull rate. |
| `segment_channels` | `3` or `4` | discovered | Override the channel count: 3 for RGB, 4 for RGBW. |
| `input_port` | string | `light` | Name of the input port. |

```nginx
graph {
    node literal blue color:srgb [[0, 0, 1]];
    node GoveeLight lamp {
        host "192.168.1.70";
        fps 10;
        connect blue;
    }
}
```
