# @rasl/color

Color space conversion utilities for RASL.

## Overview

This package provides perceptually uniform color space conversions, optimized for smooth animations and LED lighting applications.

## Supported Color Models

| Model | Description | Best For |
|-------|-------------|----------|
| `srgb` | Standard RGB (0-1 range) | Display output |
| `linear` | Linear RGB | Blending operations |
| `hsl` | Hue, Saturation, Lightness | Traditional color picking |
| `oklab` | Oklab perceptual (L, a, b) | Perceptual blending |
| `oklch` | Oklab cylindrical (L, C, H) | Chroma/hue control |
| `okhsl` | Perceptually uniform HSL | **Hue animations** |
| `okhsv` | Perceptually uniform HSV | Value-based effects |

## Key Types

```typescript
const ColorModel = {
  Srgb: 'srgb',
  Linear: 'linear',
  Hsl: 'hsl',
  Oklab: 'oklab',
  Oklch: 'oklch',
  Okhsl: 'okhsl',
  Okhsv: 'okhsv',
} as const;
type ColorModel = (typeof ColorModel)[keyof typeof ColorModel];
```

## Usage

```typescript
import { convert, ColorModel } from '@rasl/color';

// Convert sRGB to OkHSL for smooth hue animation
const rgb: [number, number, number] = [1.0, 0.5, 0.0];
const okhsl = convert(rgb, ColorModel.Srgb, ColorModel.Okhsl);

// Animate hue uniformly
okhsl[0] = (okhsl[0] + 0.01) % 1.0;

// Convert back to sRGB for output
const result = convert(okhsl, ColorModel.Okhsl, ColorModel.Srgb);
```

## Why OkHSL for Animations?

Traditional HSL has non-uniform hue perception - some hues appear brighter than others. OkHSL provides:

- **Uniform hue distribution** - All hues appear equally vibrant
- **Consistent lightness** - No brightness jumps during hue rotation
- **Smooth gradients** - Better interpolation between colors

## Conversion Architecture

All conversions route through Oklab as the hub space:

```
sRGB ↔ Linear RGB ↔ Oklab ↔ Oklch
                      ↕
                   OkHSL/OkHSV
                      
HSL ↔ sRGB (direct)
```
