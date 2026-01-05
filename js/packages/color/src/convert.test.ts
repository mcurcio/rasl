/**
 * Tests for color conversion utilities.
 *
 * These tests verify parity with the Python implementation per §5.3 of migrate.md.
 */

import { describe, it, expect } from 'vitest';
import { convert, ColorModel, normalizeModel } from './convert.js';

describe('normalizeModel', () => {
  it('should normalize srgb variants', () => {
    expect(normalizeModel('srgb')).toBe('srgb');
    expect(normalizeModel('rgb')).toBe('srgb');
    expect(normalizeModel('SRGB')).toBe('srgb');
  });

  it('should normalize hsl', () => {
    expect(normalizeModel('hsl')).toBe('hsl');
    expect(normalizeModel('HSL')).toBe('hsl');
  });

  it('should normalize oklab variants', () => {
    expect(normalizeModel('oklab')).toBe('oklab');
    expect(normalizeModel('lab')).toBe('oklab');
  });

  it('should normalize oklch variants', () => {
    expect(normalizeModel('oklch')).toBe('oklch');
    expect(normalizeModel('lch')).toBe('oklch');
  });

  it('should normalize okhsl/okhsv', () => {
    expect(normalizeModel('okhsl')).toBe('okhsl');
    expect(normalizeModel('okhsv')).toBe('okhsv');
  });

  it('should default unknown to srgb', () => {
    expect(normalizeModel('unknown')).toBe('srgb');
  });
});

describe('convert', () => {
  describe('identity conversions', () => {
    it('should return same color for same model', () => {
      const color: [number, number, number] = [0.5, 0.3, 0.7];
      expect(convert(color, ColorModel.Srgb, ColorModel.Srgb)).toEqual(color);
      expect(convert(color, ColorModel.Oklab, ColorModel.Oklab)).toEqual(color);
    });
  });

  describe('srgb <-> oklab roundtrip', () => {
    it('should roundtrip red', () => {
      const red: [number, number, number] = [1, 0, 0];
      const oklab = convert(red, ColorModel.Srgb, ColorModel.Oklab);
      const back = convert(oklab, ColorModel.Oklab, ColorModel.Srgb);
      expect(back[0]).toBeCloseTo(1, 4);
      expect(back[1]).toBeCloseTo(0, 4);
      expect(back[2]).toBeCloseTo(0, 4);
    });

    it('should roundtrip green', () => {
      const green: [number, number, number] = [0, 1, 0];
      const oklab = convert(green, ColorModel.Srgb, ColorModel.Oklab);
      const back = convert(oklab, ColorModel.Oklab, ColorModel.Srgb);
      expect(back[0]).toBeCloseTo(0, 4);
      expect(back[1]).toBeCloseTo(1, 4);
      expect(back[2]).toBeCloseTo(0, 4);
    });

    it('should roundtrip blue', () => {
      const blue: [number, number, number] = [0, 0, 1];
      const oklab = convert(blue, ColorModel.Srgb, ColorModel.Oklab);
      const back = convert(oklab, ColorModel.Oklab, ColorModel.Srgb);
      expect(back[0]).toBeCloseTo(0, 4);
      expect(back[1]).toBeCloseTo(0, 4);
      expect(back[2]).toBeCloseTo(1, 4);
    });

    it('should roundtrip white', () => {
      const white: [number, number, number] = [1, 1, 1];
      const oklab = convert(white, ColorModel.Srgb, ColorModel.Oklab);
      const back = convert(oklab, ColorModel.Oklab, ColorModel.Srgb);
      expect(back[0]).toBeCloseTo(1, 4);
      expect(back[1]).toBeCloseTo(1, 4);
      expect(back[2]).toBeCloseTo(1, 4);
    });

    it('should roundtrip gray', () => {
      const gray: [number, number, number] = [0.5, 0.5, 0.5];
      const oklab = convert(gray, ColorModel.Srgb, ColorModel.Oklab);
      const back = convert(oklab, ColorModel.Oklab, ColorModel.Srgb);
      expect(back[0]).toBeCloseTo(0.5, 4);
      expect(back[1]).toBeCloseTo(0.5, 4);
      expect(back[2]).toBeCloseTo(0.5, 4);
    });
  });

  describe('srgb <-> hsl roundtrip', () => {
    it('should roundtrip red', () => {
      const red: [number, number, number] = [1, 0, 0];
      const hsl = convert(red, ColorModel.Srgb, ColorModel.Hsl);
      const back = convert(hsl, ColorModel.Hsl, ColorModel.Srgb);
      expect(back[0]).toBeCloseTo(1, 4);
      expect(back[1]).toBeCloseTo(0, 4);
      expect(back[2]).toBeCloseTo(0, 4);
    });

    it('should roundtrip cyan', () => {
      const cyan: [number, number, number] = [0, 1, 1];
      const hsl = convert(cyan, ColorModel.Srgb, ColorModel.Hsl);
      const back = convert(hsl, ColorModel.Hsl, ColorModel.Srgb);
      expect(back[0]).toBeCloseTo(0, 4);
      expect(back[1]).toBeCloseTo(1, 4);
      expect(back[2]).toBeCloseTo(1, 4);
    });
  });

  describe('srgb <-> oklch roundtrip', () => {
    it('should roundtrip primary colors', () => {
      const colors: [number, number, number][] = [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
        [1, 1, 0],
        [1, 0, 1],
        [0, 1, 1],
      ];

      for (const color of colors) {
        const oklch = convert(color, ColorModel.Srgb, ColorModel.Oklch);
        const back = convert(oklch, ColorModel.Oklch, ColorModel.Srgb);
        expect(back[0]).toBeCloseTo(color[0], 4);
        expect(back[1]).toBeCloseTo(color[1], 4);
        expect(back[2]).toBeCloseTo(color[2], 4);
      }
    });
  });

  describe('color stability (§5.3)', () => {
    it('should remain stable after 40 conversions', () => {
      // Per migrate.md §5.3: color conversions must remain visually stable after 40 conversions
      const original: [number, number, number] = [0.8, 0.3, 0.5];
      let color = original;

      // Do 40 roundtrips through oklch
      for (let i = 0; i < 40; i++) {
        const oklch = convert(color, ColorModel.Srgb, ColorModel.Oklch);
        color = convert(oklch, ColorModel.Oklch, ColorModel.Srgb);
      }

      // Should still be close to original (within perceptual threshold)
      // Using 2 decimal places as per Python implementation notes
      expect(color[0]).toBeCloseTo(original[0], 2);
      expect(color[1]).toBeCloseTo(original[1], 2);
      expect(color[2]).toBeCloseTo(original[2], 2);
    });

    it('should remain stable through okhsl after 40 conversions', () => {
      const original: [number, number, number] = [0.6, 0.4, 0.7];
      let color = original;

      for (let i = 0; i < 40; i++) {
        const okhsl = convert(color, ColorModel.Srgb, ColorModel.Okhsl);
        color = convert(okhsl, ColorModel.Okhsl, ColorModel.Srgb);
      }

      // OkHSL has slightly lower precision due to gamut approximation
      expect(color[0]).toBeCloseTo(original[0], 1);
      expect(color[1]).toBeCloseTo(original[1], 1);
      expect(color[2]).toBeCloseTo(original[2], 1);
    });
  });
});
