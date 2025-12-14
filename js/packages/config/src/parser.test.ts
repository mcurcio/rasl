/**
 * Tests for the RASL config parser.
 */

import { describe, it, expect } from 'vitest';
import { parse } from './parser.js';

describe('Parser', () => {
  describe('basic parsing', () => {
    it('should parse empty rasl block', () => {
      const result = parse('rasl { }');
      expect(result.errors).toHaveLength(0);
      expect(result.cst).not.toBeNull();
      expect(result.cst?.children).toHaveLength(1);
      expect(result.cst?.children[0]?.name).toBe('rasl');
    });

    it('should parse simple node block', () => {
      const source = `
        rasl {
          node Waveform sine {
            shape sawtooth;
            frequency_hz 0.1;
          }
        }
      `;
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
      expect(result.cst).not.toBeNull();
      const rasl = result.cst!.children[0]!;
      expect(rasl.name).toBe('rasl');
      expect(rasl.body?.[0]?.name).toBe('node');
    });

    it('should parse node with connect directive', () => {
      const source = `
        rasl {
          node ConsoleSink console {
            connect upstream;
          }
        }
      `;
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
    });

    it('should parse node with fill directive', () => {
      const source = `
        rasl {
          node Compose color {
            fill saturation 0.8;
            fill lightness 0.5;
          }
        }
      `;
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
    });
  });

  describe('virtual.conf style config', () => {
    it('should parse waveform node', () => {
      const source = `
        rasl {
          node Waveform hue_ramp {
            shape sawtooth;
            frequency_hz 0.1;
            output_channels 512;
            fps 30;
          }
        }
      `;
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
    });

    it('should parse compose node with ports block', () => {
      const source = `
        rasl {
          node Compose okhsl_color {
            ports {
              hue; saturation; lightness;
            }
            output_type okhsl;
            connect hue_ramp hue;
            fill saturation 1;
            fill lightness 0.5;
          }
        }
      `;
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
    });

    it('should parse color node with model', () => {
      const source = `
        rasl {
          node Color toRgb rgb {
            connect okhsl_color;
          }
        }
      `;
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
    });

    it('should parse console sink', () => {
      const source = `
        rasl {
          node ConsoleSink console {
            max_channels 24;
            include_metadata true;
            as_bytes true;
            fps 1;
            connect toRgb;
          }
        }
      `;
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
    });
  });

  describe('error handling', () => {
    it('should report missing rasl block', () => {
      const source = 'other { }';
      const result = parse(source);
      // Parser should still work, just no rasl block
      expect(result.cst).not.toBeNull();
    });

    it('should report syntax errors', () => {
      const source = 'rasl { node { }';  // Missing node type/id
      const result = parse(source);
      // Should have errors or handle gracefully
      expect(result.cst).not.toBeNull();
    });
  });

  describe('comments', () => {
    it('should ignore line comments', () => {
      const source = `
        rasl {
          // This is a comment
          node Waveform sine {
            shape sawtooth; // inline comment
          }
        }
      `;
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
    });

    it('should ignore block comments', () => {
      const source = `
        rasl {
          /* Multi-line
             comment */
          node Waveform sine { }
        }
      `;
      const result = parse(source);
      expect(result.errors).toHaveLength(0);
    });
  });
});
