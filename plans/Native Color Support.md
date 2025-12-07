# Cascade Chat Conversation

  Note: _This is purely the output of the chat conversation and does not contain any raw data, codebase snippets, etc. used to generate the output._

### User Input

I want to support the idea of Colors natively. I want some mechanism to map an input or an output as dealing with "Color" and pootentially also flagging it against a color space like RGB or HSL. That way I can do internal transformations in color space and have them mapped correctly to the outputs.

For example: say I want to take the sine source, and use it a generator to produce "rainbow chasing colors" down a string. I can add a transformer node downstream of the sine which modifies the frames to produce `(sine, 1, 1)` tuples and flag the output as HSL. Then I can map that to an SACN sink that is configured for RGB.

Lets talk through some design options and tradeoff considerations of this feature.

### Planner Response

You’re describing two related needs:

- Semantically tagging data as “this is color, in X color space”
- Having the engine/sinks use that information to do the right conversions without you manually juggling RGB/HSL/etc.

Below are some design axes and concrete options, then I’ll suggest a phased approach.

---

## 1. Key Design Axes

When you say “support Colors natively”, there are a few big questions:

- **[Representation]** Is a color a first-class type in the engine, or just metadata on top of existing numeric arrays?
- **[Scope]** Is color space a per-port thing, per-frame field, or global to a node?
- **[Conversion location]** Where do conversions happen?
  - Explicit transform nodes only?
  - At sinks?
  - Auto-inserted nodes at graph build time?
- **[Strictness]** Should mismatched spaces be an error, a warning, or auto-converted “magically”?
- **[Semantics depth]** Do we care only about `RGB` vs `HSL`, or also encoding (linear vs sRGB), range (0–1 vs 0–255), etc.?

Your sine → HSL → sACN(RGB) example suggests:

- You want to **work in HSL internally** (e.g. manipulating hue).
- You want the **sink to understand** that input is HSL and it needs RGB.
- You’d like **automatic, correct conversion** at the interface.

---

## 2. Option A: Color as a First-Class Data Type

Here “color” becomes an explicit type in the engine.

### Sketch

- Define a `ColorSpace` enum: `rgb`, `hsl`, `hsv`, maybe `rgb_linear`, etc.
- A data wrapper, conceptually:

  ```python
  class ColorArray:
      data: np.ndarray  # (..., 3) or (..., 4)
      space: ColorSpace
      # maybe range, encoding, component labels
  ```

- Schemas/ports can declare they carry `ColorArray` instead of plain `Array`:
  - `kind="color"`, `space="hsl"`, `channels=3` at the type level.
- Color-aware transforms/sinks operate on `ColorArray`, call `convert_to(...)` when needed.

### Pros

- **Strong semantics**: The type system knows “this is color” vs generic numeric data.
- **Good introspection/validation**: You can validate connections (HSL→HSL OK, HSL→RGB maybe auto-convert or error).
- **Extendable**: Easy to add more spaces later.

### Cons

- **Invasive**: Touches schemas, node interfaces, plugins; every color-related plugin must speak this type.
- **Mixed worlds**: Many nodes still deal with `np.ndarray` only; you’ll need bridging logic.
- **Higher upfront complexity**: Bigger refactor for an alpha-stage engine.

---

## 3. Option B: Color as Schema/Port Metadata (Tagging Existing Arrays)

Here, values stay as they are (e.g. `np.ndarray` of shape `(n_pixels, 3)`), but ports/frames carry **metadata** saying “this is color, in HSL”.

### Sketch

- Extend existing port/channel schema to include **optional** color semantics, e.g.:

  ```yaml
  kind: "array"
  channels: 3
  semantics:
    role: "color"
    space: "hsl"      # or "rgb"
    encoding: "linear"  # or "srgb"
    range: "0-1"      # or "0-255"
  ```

- Internally, you keep using the same `Frame`/array types.
- Color-specific transforms and sinks **inspect this metadata**:
  - E.g. an `HSLHueRotate` transform checks `semantics.space == "hsl"`.
  - An sACN sink states `semantics.role="color", space="rgb", encoding="srgb", range="0-255"`.

### Pros

- **Minimal disruption**: Engine core stays mostly the same; you’re just enriching schemas.
- **Backwards compatible**: Existing nodes keep working; only new ones opt into color semantics.
- **Gradual adoption**: You can start with one sink (sACN) and a couple of transforms.

### Cons

- **Weaker type safety**: It’s easier to accidentally ignore semantics and treat RGB as generic floats.
- **Rely on conventions**: Everyone must agree on `space`, `range`, etc. strings.
- **Conversion behavior** must be encoded in sinks/transforms; engine core is more passive.

---

## 4. Option C: Canonical Internal Color Space

Another axis: do you want a **canonical internal representation**?

- E.g. “inside RASL, colors are always `linear_rgb, range 0–1`”
- Anything that wants HSL converts at its boundary; sinks convert from canonical → device encoding.

### Pros

- **Predictable math**: All blending/compositing can assume linear RGB, avoiding gamma mistakes.
- **Less metadata explosion**: Many nodes can ignore space and just assume canonical.

### Cons

- **More conversions**: HSL-heavy graphs do HSL→RGB→HSL a lot unless you’re careful.
- **Less flexible** if you later want to support radically different models (e.g. Lab, HCL) as first-class.

You could also choose **no canonical space**, and let each node declare what it emits/accepts; conversions happen at mismatches only.

---

## 5. Where Should Conversion Happen?

Given your example, there are a few plausible policies:

### 5.1. Explicit Color-Conversion Transforms Only

- You’d write:

  ```text
  sine → hsl_mapper → hsl_to_rgb → sacn_rgb_sink
  ```

- Engine won’t convert for you; semantics used only by transforms to assert/validate.

**Pros**

- Very explicit, zero magic.
- Easy to reason about performance.

**Cons**

- Cluttered graphs: you end up sprinkling `hsl_to_rgb` and `rgb_to_hsl` everywhere.
- Not aligned with your “HSL → RGB sink” mental model.

### 5.2. Conversion in Sinks (Edge Conversion)

- You have:

  ```text
  sine → hsl_mapper (outputs HSL) → sacn_sink(configured for RGB)
  ```

- sACN sink:
  - Declares `input_semantics = {role: "color", space: "rgb", ...}`.
  - At runtime, sees `upstream_space == "hsl"` → calls `hsl_to_rgb()` before packing DMX.

**Pros**

- Matches your example: you just tag HSL and configure sink as RGB; conversion is implicit at sink boundary.
- Each sink defines what it expects; works well for device-specific encodings (RGB, HSBK, etc.).

**Cons**

- Doesn’t help when a *transform* expects a particular space (e.g. HueRotate wants HSL but upstream is RGB).
- Conversion logic is duplicated if many sinks need it, unless factored into shared color utilities.

### 5.3. Auto-Inserted Conversion Nodes

- Graph builder detects that port A (HSL) connects to port B (RGB).
- It injects an implicit node `HSLtoRGB` between them.

**Pros**

- Clean graphs but with explicit nodes under the hood.
- Potentially good UX if debug tooling shows those nodes.

**Cons**

- More “magic”: harder to predict performance and behavior.
- More complicated graph-building/type-checker logic.

---

## 6. Semantics Detail Level

You mentioned just `RGB` vs `HSL`, but for correctness you’ll likely care about:

- **Space**: `rgb`, `hsl`, `hsv`, `hsbk`, etc.
- **Encoding/transfer**: `linear`, `srgb`, maybe device-specific.
- **Range**: `0–1`, `0–255`, `0–65535`...
- **Components**: labels (`["r","g","b"]`, `["h","s","l"]`) for clarity and UI.

A reasonable v1 might be:

- Required: `role: "color"`, `space: "rgb"|"hsl"`.
- Recommended: `range: "0-1"` or `"0-255"`.
- Optional (but forward-looking): `encoding: "linear"|"srgb"`.

---

## 7. Applying These to Your Example

**Goal**: Sine → rainbow chase in HSL → sACN RGB output.

### With Option B + Sink-Side Conversion

- A transform that takes scalar sine and emits a 3-channel array with semantics:

  ```python
  semantics = {
      "role": "color",
      "space": "hsl",
      "range": "0-1",
      "components": ["h", "s", "l"],
  }
  ```

  and values `(sine, 1, 0.5)`.

- sACN sink declares:

  ```python
  expected_semantics = {
      "role": "color",
      "space": "rgb",
      "range": "0-255",
      "encoding": "srgb",
  }
  ```

- Sink logic:

  1. Validate that upstream `role == "color"`.
  2. If `space != "rgb"`, call `convert_color(data, from_space=upstream_space, to_space="rgb")`.
  3. If `range != "0-255"`, rescale.
  4. If `encoding != "srgb"`, apply gamma.

You get your desired behavior without extra explicit nodes.

---

## 8. Recommended Path (Incremental)

Given RASL’s “explicit over magic” philosophy and current alpha stage, I’d lean toward:

1. **Phase 1 – Metadata + Utilities (Low Risk)**
   - Add optional color semantics to port/channel schemas (`role`, `space`, `range`, `encoding`).
   - Create a small `colors` module with:
     - `ColorSpace` enum or string constants.
     - `hsl_to_rgb`, `rgb_to_hsl` (vectorized, NumPy).
     - Helpers for range and encoding conversion.
   - Teach *one* sink (sACN) and *one* transform to use it as a proof of concept.

2. **Phase 2 – Sink-Side Auto Conversion**
   - Establish a standard for sinks:
     - They declare an expected color semantics spec.
     - On mismatch, they either:
       - Convert automatically (default), or
       - Throw a validation error if auto-conversion disabled.
   - Provide a config knob per sink: `auto_color_convert=True/False`.

3. **Phase 3 – Optional Graph-Level Reasoning**
   - If needed, add type-checking that warns/error on mismatched `role/space/range` without a clear conversion path.
   - Potentially auto-insert conversion nodes in some cases (opt-in).

4. **Phase 4 – Consider First-Class Color Type (If Needed)**
   - If color becomes pervasive, migrate from “metadata on arrays” to an explicit `ColorArray` type for better DX and introspection.

---

## 9. Questions to Narrow the Design

To make this concrete in your codebase:

- **Ranges/encoding**:
  - Are you okay standardizing *internal* colors as floats `0–1`, possibly `linear_rgb`?
  - Or do you want to allow nodes to freely choose `0–255` etc. and rely on semantics?
- **Magic level**:
  - For v1, do you want sinks to **auto-convert** when spaces differ, or should that only happen if a flag is set?
- **Scope**:
  - Do you want semantics attached **per port** (entire frame field) or per **channel group** (e.g. multiple color fields in one frame)?
- **Future spaces**:
  - Near-term, are `RGB` and `HSL` enough, or do you foresee wanting `HSV`, `HSBK`, or perceptual spaces (Lab/LCh) soon?

If you answer those, I can sketch a more concrete schema shape and how a sine→HSL→sACN graph would look in actual RASL code.

### User Input

I think "support Colors natively" means having some first-class metadata attached to Frames (or elements within the frame) that help guard whether those ports can be connected. IF they dont match, include RGB!=HSL, then a connection would fail and an explicit transformer node would need to be added. Im not advocating for implicit conversions.

linear vs sRGB could be another type, or another axis in existing RGB space (honestly, I dont know enough color theory to build a clean domain model). But range [0, 1] should be fairly non-negotiable so long as python supports double precision. I *could* see having distinct Frame types (or Datum(?) types in a Frame?) where we want things strongly typed. If nodes can _only_ connect to types they have declared as compatible, then it wouldnt be difficult to manage each having a different object representation.

Brainstorm some techniques for giving us "type safety" without adding too much overhead for nodes to implement. Be concise in your response.

### Planner Response

You’re basically asking: “How do I get *real* type safety around color (RGB vs HSL, etc.) with explicit conversions, without making every node author write a bunch of boilerplate?”

Below are concrete techniques that fit that goal.

---

## 1. A Small, First-Class `DatumType` (or `PortType`)

Define a lightweight, immutable descriptor used in port schemas:

```python
class DatumType(NamedTuple):
    kind: Literal["scalar", "vector", "color", "index", "mask", "any"]
    space: str | None        # "rgb", "hsl", "hsv", etc.
    encoding: str | None     # "linear", "srgb", ...
    range_01: bool | None    # True for [0,1], False for something else, None = unknown
    channels: int | None     # e.g. 3 for RGB/HSL
```

Add cheap helpers so node authors rarely touch fields directly:

```python
ColorRGB = DatumType(kind="color", space="rgb", encoding="srgb", range_01=True, channels=3)
ColorHSL = DatumType(kind="color", space="hsl", encoding=None, range_01=True, channels=3)
AnyColor = DatumType(kind="color", space=None, encoding=None, range_01=None, channels=3)
AnyType  = DatumType(kind="any", space=None, encoding=None, ...)
```

Ports then declare just:

```python
in_type = ColorHSL
out_type = ColorHSL
# or
in_type = AnyColor
```

Engine uses `DatumType` only for **connection validation**; actual runtime value can stay a `np.ndarray`.

---

## 2. Structural Compatibility Rules (No Implicit Conversion)

Implement a simple `is_compatible(src: DatumType, dst: DatumType) -> bool`:

- **Exact match** → ok.
- `dst.kind == "any"` → ok.
- `dst.kind == "color"` and `dst.space is None` → accept any color (for generic color nodes).
- Otherwise: `False` (e.g. `rgb` vs `hsl` mismatches).

This is enforced at **graph-build time** when connecting ports:

- If incompatible, connection fails with a clear message (“expected Color[space=rgb], got Color[space=hsl]”).
- No automatic conversion; user must add explicit `HSL→RGB` node.

You can extend compatibility with more axes (encoding, range) when you’re ready, without changing node code.

---

## 3. Defaulting & Pass-Through to Minimize Node Author Work

To reduce overhead:

- **If a node doesn’t declare `DatumType`**, treat all its ports as `AnyType`:
  - No checks, fully permissive.
  - Great for quick/internal nodes.
- Provide **base classes** that handle “copy input type to output type” automatically:

  ```python
  class UnaryPassThrough(Node):
      input_type: DatumType = AnyType
      output_type: DatumType | None = None  # None = "same as input"

      def infer_output_type(self, input_type: DatumType) -> DatumType:
          return self.output_type or input_type
  ```

  Then a simple scalar map node only needs to pick a base class; no custom type logic.

- For *color-preserving* transforms (e.g. hue shifts in HSL that keep HSL type), provide:

  ```python
  class ColorPreserving(Node):
      input_type: DatumType = AnyColor

      def infer_output_type(self, input_type: DatumType) -> DatumType:
          assert input_type.kind == "color"
          return input_type
  ```

Node authors often just inherit from one of these and write `process(frame)`; types “just work”.

---

## 4. Stronger Typing When You Want It (Distinct Data/Frame Types)

You can still introduce richer types without burden:

- At the **frame-field** level:

  ```python
  class FieldSpec(NamedTuple):
      name: str
      dtype: DatumType
  ```

  A `Frame` is then conceptually `{name -> (value, dtype)}`.
- Nodes declare which **field(s)** they read/write and their required `DatumType`.
- Engine checks connections using `FieldSpec.dtype`.

This gives the option for **distinct runtime objects** later:

- `ColorRGBArray` vs `ColorHSLArray` as specialized numpy wrappers.
- Ports for those types still just compare `DatumType`; the mapping from `DatumType` ↔ Python class is centralized, not repeated in each node.

---

## 5. Unions and Constraints for Flexibility

To avoid “RGB-only” brittleness while still being safe:

- Allow ports to declare **either** a single `DatumType` or a **constraint**:

  ```python
  class DatumConstraint(NamedTuple):
      kind: Literal["color", "scalar", ...]
      allowed_spaces: set[str] | None = None  # None => any for this kind
  ```

- Examples:

  - “Any color”: `DatumConstraint(kind="color")`
  - “Must be RGB or HSL”: `DatumConstraint(kind="color", allowed_spaces={"rgb", "hsl"})`

Compatibility check then becomes:

- If `port_type` is a `DatumType` → exact/type-based match.
- If `port_type` is a `DatumConstraint` → apply constraint.
- If `port_type` absent → `AnyType`.

Node authors then usually say **one of**:

- “I don’t care” (no type).
- “I accept any color”.
- “I require HSL” (for hue-specific math).

---

## 6. Validation Timing: Build-Time + Optional First-Frame Assert

To keep runtime overhead low:

- Do **most checks at graph construction** using declared `DatumType`/constraints.
- Optionally, on **first frame**, assert that the **runtime data shape** matches type:
  - `kind="color", channels=3` → array last-dim must be 3.
  - `range_01=True` can’t really be enforced, but you can add debug-only checks if desired.

This catches mis-wired graphs without per-frame cost.

---

## 7. Color-Specific Sugar

Finally, to make color easy but explicit:

- Provide color constants & helpers:

  ```python
  Color = SimpleNamespace(
      RGB=lambda encoding="srgb": DatumType(kind="color", space="rgb", encoding=encoding, range_01=True, channels=3),
      HSL=lambda: DatumType(kind="color", space="hsl", encoding=None, range_01=True, channels=3),
  )
  ```

- Provide color-node base classes:

  - `HSLNode` (input/output `Color.HSL()`).
  - `RGBNode` (input/output `Color.RGB()`).
  - `AnyColorNode` (constraint).

That gives you **strong, explicit color typing** + RGB≠HSL guarding, while the *average* node author usually just picks a base class or a single constant and writes no extra boilerplate.

---

**Summary:**  
Use a small `DatumType` + constraints on ports, validate at graph-build time, and hide most complexity behind base classes and constants. No implicit conversions; explicit HSL↔RGB transformers are the only way across incompatible spaces.

### User Input

1. Is `range_01` useful? nodes would already be receiving a strongly typed object, and presumably would understand its internal composition.
I do like this idea in the send that `connect` would still work: its just that instead of connecting `float`, it would be connecting `HslColor` or something.
I dont like that DatumType has a "space" encoded directly in it. It would be *nice* if DatumType was more generic. For instance, there could be a child `ColorType extends DatumType` that adds the "space" property, as "color space" is a unique property of colors.
2. Ports should be able to declare multiple inputs. If a node only wanted RGB, then it could declare Rgb as its input. Or it could declare Rgb|Hsl (somehow). Or it could more generally declare "Color" as its input to accept any valid color, which would be useful for generic color transformation or processing nodes.
3. The ability to say "i take any kind of data" really depends on how data is represented internally. If every Frame is always an array of floats, then compatibility is straightforward. But if the type of data changes the type of the array being passed around in the Frame, then generic nodes become trickier (though not impossible!). It could still work if the node is only manipulating some common property or metadata and otherwise passing throug or multiplexing the frame data.

Thats as far as I want to discuss right now. Process my notes and give me some fresh ideas. Be concise.

### Planner Response

Here are some directions that incorporate your notes and push the design a bit further.

---

## 1. Treat `[0,1]` as a Contract, Not a Type Axis

- **Drop `range_01` from the type system** and make `[0,1]` a *global invariant* for all color data.
- Nodes that violate that are simply “wrong”; you don’t need type machinery for it.
- If you later care about `[0,255]` etc., model that as a **different `ColorType`** (e.g. `DmxRgbColor`) rather than an axis on the same one.

This simplifies the descriptor and matches your “strongly typed object that understands its composition” intuition.

---

## 2. Nominal Type Tokens + Specialization for Color

Instead of a single `DatumType` with a `space` field, think:

```python
class DatumType: ...
class ColorType(DatumType): ...
class RgbColor(ColorType): ...
class HslColor(ColorType): ...
class AnyColor(ColorType): ...
class FloatScalar(DatumType): ...
# etc.
```

Characteristics:

- **Ports declare types by class (or instance) reference**, not by inspecting generic fields:
  - `input_type = RgbColor`
  - `input_type = (RgbColor, HslColor)`   # union
  - `input_type = AnyColor`               # accepts all colors
- Color space is encoded in the **specific subtype** (`RgbColor`, `HslColor`), not as a generic `space` property on the base.
- You still get generic machinery by having:
  - `issubclass(RgbColor, ColorType)` to gate “all colors”
  - `issubclass(t, DatumType)` for “any data”.

This keeps the type model generic (extendible to non-color domains) but gives color a richer specialized hierarchy.

---

## 3. Port Unions as First-Class “Accepted Types”

Ports can naturally express your “Rgb | Hsl | Color” idea:

- `input_types: tuple[type[DatumType], ...]`  
  or a small helper:

  ```python
  accepts = OneOf(RgbColor, HslColor)
  accepts = AnyOfKind(ColorType)   # any color
  accepts = AnyType()              # any DatumType
  ```

Connection rule:

- A connection is valid if **the source’s concrete type token** is compatible with *any* of the accepted tokens/constraints.
- For your `Rgb|Hsl` example:
  - `source_type is RgbColor` → ok.
  - `source_type is HslColor` → ok.
  - `source_type is FloatScalar` → reject.

This gives explicit unions without adding user-visible type algebra syntax.

---

## 4. Separate “Abstract Type” From Runtime Representation

To handle your point (3) about internal representation:

- Define **two layers**:
  - An **abstract type token** (e.g. `RgbColor`) used for connection checking.
  - A **runtime representation** (e.g. `np.ndarray`, or a `RgbFrameField` wrapper).

Let each type token define how to get at the underlying data if needed:

```python
class RgbColor(ColorType):
    storage_kind = "array"       # or "struct", "opaque", etc.
    channels = 3
    # optional: adapter API for generic nodes
```

Then:

- Nodes that **care about structure** (e.g. color math) depend on `RgbColor`, `HslColor` etc.
- Generic nodes (mux, routing, caching) just handle **“frames of opaque payloads”** and don’t look inside; they only check identity/equality of type tokens.

This keeps generic nodes feasible even if later some types aren’t simple float arrays.

---

## 5. “Any Data” and “Any Color” Without Losing Safety

A couple of fresh patterns:

- **Opaque passthrough nodes**:
  - Ports declare `input_type = AnyType` and `output_type = SameAsInput`.
  - Engine ensures they never change the type token; they’re pure routers.
- **Capability-based generic nodes**:
  - A node can say “I accept `AnyColor` but only promise to preserve type, not reinterpret it.”
  - That’s ideal for nodes that adjust timing, blend-by-alpha, or spatially rearrange pixels, but don’t care if it’s RGB or HSL.

This gives you a gradient:
- Very specific (`RgbColor` only),
- Loosely specific (`AnyColor`),
- Fully generic (`AnyType` pass-through).

---

## 6. Color-Specific Helpers to Reduce Boilerplate

To keep node author ergonomics good:

- Provide **ready-made type tokens** and base classes:
  - `RgbNode` → `input_type = RgbColor`, `output_type = RgbColor`.
  - `HslNode` → same for `HslColor`.
  - `ColorAgnosticNode` → `input_type = AnyColor`, `output_type = SameAsInput`.
- Provide **conversion nodes**:
  - `RgbToHslNode: RgbColor → HslColor`
  - `HslToRgbNode: HslColor → RgbColor`
- Connection failures clearly say:
  - “Expected `RgbColor`, got `HslColor`. Insert an `HslToRgbNode`.”

You get the explicit conversion graph you want, but the typing surface for typical node authors is: pick a base class or a type token constant.

---

If you like this direction, next step would be to sketch the minimal `DatumType` / `ColorType` hierarchy and one or two example node signatures (e.g. `HslHueShift`, `SACNRgbSink`) in your existing schema style.

### User Input

So what is the actual data being passed around? What does a frame look like? Take an example like DMX producing 512 channels of RGB -- would would it emit to the next node in the graph?

### Planner Response

Good question—this is where the type story hits the metal.

I’ll describe a concrete-but-flexible model that fits what you’ve been leaning toward.

---

## 1. Core Idea: “Strongly-Typed Payload + Float Storage”

- **Runtime payload**: one strongly-typed object per edge per frame (e.g. `RgbColorBuffer`, `HslColorBuffer`, `FloatArray`).
- **Storage**: inside those objects, it’s still **NumPy `float32` in `[0,1]`** almost everywhere.
- **Frame**: wraps timing + that payload.

Conceptually:

```python
class Frame(NamedTuple):
    t: float
    dt: float
    seq: int
    payload: Any          # actual data object
    payload_type: type    # e.g. RgbColorBuffer, HslColorBuffer, FloatArray
```

Ports constrain `payload_type`, not the concrete array layout.

---

## 2. Color Payload Example Types

For color, you might have:

```python
class ColorBuffer:
    data: np.ndarray  # (..., 3), float32 in [0,1]

class RgbColorBuffer(ColorBuffer):
    pass  # semantic: this is RGB

class HslColorBuffer(ColorBuffer):
    pass  # semantic: this is HSL
```

- Type-level checks use `RgbColorBuffer` / `HslColorBuffer` as the **token**.
- The engine doesn’t care about `data` layout beyond what generic nodes need.

---

## 3. DMX Example: “512 channels of RGB”

Assume a DMX *source* node reading a universe and producing colors:

- Universe has 512 channels → **170 full RGB triplets + 2 spare channels**.
- You decide the logical model is “170 RGB pixels”.

The **frame emitted to the next node** could look like:

```python
Frame(
    t=t,
    dt=dt,
    seq=seq,
    payload=RgbColorBuffer(
        data=np.ndarray(shape=(170, 3), dtype=np.float32)  # values in [0,1]
    ),
    payload_type=RgbColorBuffer,
)
```

So to the next node in the graph, “DMX producing 512 channels of RGB” is:

- A `Frame` whose `payload` is a `RgbColorBuffer`.
- Internally: a `(n_pixels, 3)` float array in `[0,1]`.

If you later want raw DMX:

- Define another payload type, e.g. `DmxUniverseBuffer` with `data.shape == (512,)`.
- A different node might convert `DmxUniverseBuffer → RgbColorBuffer` for higher-level color processing.

---

## 4. How This Plays With Typing

- A port that wants **only RGB** declares `input_type = RgbColorBuffer`.
- A port that accepts **any color** declares `input_type = ColorBuffer` (or `Union[RgbColorBuffer, HslColorBuffer]`).
- A port that’s generic routing declares `input_type = Any` and just passes `payload` through unchanged.

The actual thing “passed around” is always:

- A small `Frame` object containing
  - timing
  - a **strongly-typed payload object**
  - whose backing storage is still just arrays of floats.

This gives you:

- Strong type safety at the connection level.
- Clear mental model for what DMX/other nodes emit.
- Freedom to introduce non-array payloads later (e.g. event lists) without breaking generic routing nodes.

### User Input

Im not completely fluent in numpy. Is `(170, 3)` a matrix of 170 3-element arrays?

### Planner Response

Yes.

In NumPy, an array with shape `(170, 3)` means:

- It has **170 rows** and **3 columns**.
- You can think of it as **170 3-element vectors**.
- Each row is a length-3 1D array. For example, if `a` has shape `(170, 3)`:
  - `a[0]` or `a[0, :]` → a 3-element vector (e.g. one RGB triplet).
  - `a[i]` → the ith 3-element vector.

So for colors, `(170, 3)` is a natural way to represent 170 pixels, each with 3 channels (R/G/B or H/S/L).  

**Summary:** shape `(170, 3)` = 170 × 3 matrix; each of the 170 rows is a 3-element vector.

### User Input

Ok, I get it. I think I like it. So the data shape in the Frame _would_ change depending on the type, but it would be some variant of a numpy matrix. An n-dimension matrix, from vector up to arbitrarily complex many-element data type arrays?

### Planner Response

Yes, that’s a good way to think about it.

### Data shape vs. type

- **Shape depends on the semantic type**, but:
  - It’s always *some* NumPy `ndarray` (or thin wrapper around one).
  - Each type declares what shapes it expects/produces.

Examples:

- **Scalar**  
  - `FloatScalar`: shape `()` or `(1,)`
- **1D strip of RGB pixels**  
  - `RgbColorBuffer`: shape `(N, 3)`
- **2D matrix (e.g. panel)**  
  - `RgbColorBuffer`: shape `(H, W, 3)`
- **More complex structures** (e.g. multiple props, layers)  
  - Could be `(objects, points, 3)` or even `(layers, H, W, 3)` if you decide that’s useful.

### N‑dimensional, but with per‑type invariants

- Conceptually: **“n‑dimensional float array + type token”**.
- Each type (e.g. `RgbColorBuffer`, `HslColorBuffer`, `FloatArray`) defines:
  - What shapes it considers valid.
  - How to interpret those dimensions (pixels, channels, etc.).

Generic nodes don’t need to know the exact shape; they can:

- Treat the payload as an opaque object and just pass it through, **or**
- Rely on simple invariants (e.g. “last dimension is channels”) if they’re color-aware.

So yes: the *Frame*’s `payload` shape can change with type, but it’s always a NumPy array (possibly wrapped) with type-specific rules about what that array means.

### User Input

Ok, I can get on board with this model. Lets assume we're going with this and dig a little deeper. Show me a high level design of a transformer node that can take in "any color" and produce one specific color space (in this example, configure it to produce RGB output). I want to use this as a thought experiment to help inform the overall design.

### Planner Response

You’re imagining a generic “color normalizer” node that accepts any color-ish payload and outputs a specific space (RGB in this case). I’ll sketch a high-level design focused on types, contracts, and ergonomics, not full implementation.

Since this is mostly conceptual and not yet wiring into your actual codebase, I won’t touch files; I’ll just outline classes, methods, and data flow so we can reason about the design.Here’s a concrete thought-experiment design for a `ColorToRgb` transformer node, assuming the “strongly typed payload + NumPy array” model we just agreed on.

I’ll focus on contracts and data flow, not implementation details.

---

## 1. Type + Payload Model (Recap)

### Color payload base

```python
class ColorBuffer:
    """
    Base class for all color payloads.
    Backing storage is a float32 ndarray in [0,1].
    """
    def __init__(self, data: np.ndarray):
        self.data = data  # e.g. (N, 3) or (H, W, 3)
```

### Specific color spaces

```python
class RgbColorBuffer(ColorBuffer):
    """Semantics: RGB in [0,1]"""

class HslColorBuffer(ColorBuffer):
    """Semantics: HSL in [0,1]"""

# Later: HsvColorBuffer, HsbkColorBuffer, etc.
```

### Frames

```python
class Frame(NamedTuple):
    t: float
    dt: float
    seq: int
    payload: Any             # e.g. RgbColorBuffer, HslColorBuffer
```

The **type** of the edge is “payload class”, e.g. `RgbColorBuffer`, and that’s what ports talk about.

---

## 2. Port Typing for “Any Color → RGB”

### Type-level contracts

- **Input port**: accepts **any color buffer**, i.e. any subclass of `ColorBuffer`.
- **Output port**: always produces `RgbColorBuffer`.

Expressed conceptually:

```python
class ColorToRgb(Node):
    # “Any color”:
    input_accepts: type = ColorBuffer      # means: any subclass is OK
    # “Always RGB out”:
    output_type: type = RgbColorBuffer
```

Connection rule at graph-build time:

- For an upstream edge with type `UpType`:
  - Check `issubclass(UpType, ColorBuffer)` to allow connection.
  - Otherwise reject with “expected ColorBuffer, got FloatArray” etc.
- The output edge type of this node is **always** `RgbColorBuffer`.

No implicit conversions anywhere else; this node is the explicit conversion boundary.

---

## 3. Conversion Registry (So Node Logic Stays Simple)

Rather than hardcoding HSL→RGB, HSV→RGB, etc. in the node, factor that into a registry:

```python
class ColorConversionError(Exception):
    pass

class ColorConverterRegistry:
    _table: dict[tuple[type, type], Callable[[ColorBuffer], ColorBuffer]] = {}

    @classmethod
    def register(cls, src: type, dst: type, fn):
        cls._table[(src, dst)] = fn

    @classmethod
    def convert(cls, payload: ColorBuffer, dst_type: type) -> ColorBuffer:
        src_type = type(payload)
        if src_type is dst_type:
            return payload
        key = (src_type, dst_type)
        if key not in cls._table:
            raise ColorConversionError(f"No conversion {src_type.__name__} → {dst_type.__name__}")
        return cls._table[key](payload)
```

Registrations (elsewhere):

```python
ColorConverterRegistry.register(
    HslColorBuffer, RgbColorBuffer,
    lambda hsl: RgbColorBuffer(hsl_to_rgb(hsl.data))
)
# Later: registry entries for other color pairs.
```

---

## 4. Node Execution Semantics

High-level `process` for `ColorToRgb`:

```python
class ColorToRgb(Node):
    input_accepts = ColorBuffer            # any color
    output_type = RgbColorBuffer

    def process(self, frame: Frame) -> Frame:
        payload = frame.payload
        assert isinstance(payload, ColorBuffer)  # guaranteed by type checker

        # Convert to RGB if needed
        rgb_payload = ColorConverterRegistry.convert(
            payload,
            RgbColorBuffer,
        )

        # Produce new frame with same timing, new payload
        return Frame(
            t=frame.t,
            dt=frame.dt,
            seq=frame.seq,
            payload=rgb_payload,
        )
```

Behavior:

- If upstream already gives `RgbColorBuffer`, this is basically a no-op (fast path).
- If upstream gives `HslColorBuffer`, it uses the registered converter.
- If some color space doesn’t have a converter to RGB, you get a **clear runtime error**:
  - “No conversion HsvColorBuffer → RgbColorBuffer”  
  which is a signal that you either need a different explicit node or to add that mapping.

---

## 5. How This Informs the Overall Design

- **Ports express “any color” via a base class constraint** (`ColorBuffer`).
- **Concrete color spaces are explicit types** (`RgbColorBuffer`, `HslColorBuffer`).
- **No implicit edges**: RGB≠HSL, but explicit transformer nodes can handle “any color → X”.
- Conversion complexity is centralized in **a registry**, not duplicated in every node.
- This same pattern works for other domains:
  - Base `GeometryBuffer` with `MeshBuffer`, `PointCloudBuffer`, etc.
  - Base `AudioBuffer` with multiple layouts.

If you want, next we can sketch how the type checker would look at a small graph using this node (e.g. `HslGenerator → ColorToRgb → SACNSink`) and what errors/warnings you’d expect.

### User Input

No, I dont want a hardcoded ToRgbNode. I want a generic ColorConvert node that I can configure at runtime. The config might look like `node ColorTransformNode toRgb { output_space rgb; }`

### Planner Response

You’re right, a generic, configurable `ColorConvert` node is a better primitive than a hardcoded `ToRgb`.

Below is a *high-level* design that keeps strong typing but allows the “`toRgb`” behavior via config.

---

## 1. Types & Registry (Recap)

Assume:

```python
class ColorBuffer: ...
class RgbColorBuffer(ColorBuffer): ...
class HslColorBuffer(ColorBuffer): ...
# etc.
```

A **conversion registry**:

```python
class ColorConverterRegistry:
    _table: dict[tuple[type, type], Callable[[ColorBuffer], ColorBuffer]] = {}

    @classmethod
    def register(cls, src: type, dst: type, fn): ...
    @classmethod
    def convert(cls, payload: ColorBuffer, dst_type: type) -> ColorBuffer: ...
```

And a simple mapping from “space name” → payload type:

```python
COLOR_SPACES = {
    "rgb": RgbColorBuffer,
    "hsl": HslColorBuffer,
    # ...
}
```

---

## 2. ColorConvert Node: “Any Color → Configured Color”

### Type contract

- **Input**: any `ColorBuffer` subclass.
- **Output**: `ColorBuffer` in the configured space.

Conceptually:

```python
class ColorConvert(Node):
    class Config(BaseModel):
        output_space: Literal["rgb", "hsl", "hsv"] = "rgb"

    input_accepts: type = ColorBuffer  # any color

    def resolve_output_type(self) -> type[ColorBuffer]:
        return COLOR_SPACES[self.config.output_space]
```

Graph/type checker:

- When building the graph, it calls `node.resolve_output_type()` and sets the outgoing edge’s type to that class (e.g. `RgbColorBuffer`).
- Downstream nodes see a precise type (e.g. “this edge is RGB”), not “any color”.

### Runtime execution

```python
class ColorConvert(Node):
    ...

    def process(self, frame: Frame) -> Frame:
        src_payload = frame.payload
        assert isinstance(src_payload, ColorBuffer)  # guaranteed by checker

        dst_type = self.resolve_output_type()
        dst_payload = ColorConverterRegistry.convert(src_payload, dst_type)

        return Frame(
            t=frame.t, dt=frame.dt, seq=frame.seq,
            payload=dst_payload,
        )
```

---

## 3. How This Maps to Your DSL Idea

Your example:

```txt
node ColorTransformNode toRgb {
  output_space rgb;
}
```

Conceptual mapping:

- `ColorTransformNode` → instance of `ColorConvert`.
- `toRgb` / `output_space rgb` → `config.output_space = "rgb"`.
- Type checker:
  - Input: `ColorBuffer` (any color).
  - Output: `COLOR_SPACES["rgb"]` → `RgbColorBuffer`.

So in a graph:

```txt
HslGenerator     : HslColorBuffer
    → ColorConvert(output_space=rgb) : RgbColorBuffer
    → SACNSink(accepts=RgbColorBuffer)
```

Connections:

- `HslGenerator → ColorConvert` ok: `HslColorBuffer` is a `ColorBuffer`.
- `ColorConvert → SACNSink` ok: both `RgbColorBuffer`.
- If you reconfigure `output_space hsl` and reload, downstream connections that require RGB will now fail type-check.

---

## 4. Design Tradeoffs / Clarifications

- **Static vs dynamic config**:
  - If `output_space` is allowed to change at runtime *without* rebuilding the graph, it would change the output type while connections are live → type safety breaks.
  - Cleanest: treat `output_space` as **graph-time config**:
    - Changing it triggers a **rebuild/re-type-check** of the graph (which you’re already doing on script reload).
- **No implicit conversions**:
  - Nothing auto-converts except inside explicit `ColorConvert` (or similar nodes).
  - RGB≠HSL on direct edges still produce a type error; you insert `ColorConvert` to bridge.

---

If you like this, next we can apply the same pattern to a *sink* (e.g. sACN configured for RGB) and see how a generic `ColorConvert` naturally composes in front of it.