/**
 * Tests for RangeMapNode.
 */

import { describe, it, expect } from 'vitest';
import { RangeMapNode } from './range-map.js';
import { MatrixPayload, Frame, EMPTY_METADATA, InputPort, OutputPort } from '../../runtime/index.js';

function createFrame(data: number[], channels: number): Frame {
  return new Frame({
    topic: 'test',
    timestamp: 0,
    payload: new MatrixPayload(data, channels),
    metadata: EMPTY_METADATA,
  });
}

function setInputFrame(port: InputPort | null, frame: Frame): void {
  if (port) {
    port._setFrame(frame);
  }
}

function getOutputFrame(port: OutputPort | null): Frame | null {
  if (port) {
    return port._consume();
  }
  return null;
}

describe('RangeMapNode', () => {
  describe('construction', () => {
    it('should create with valid ranges', () => {
      const node = new RangeMapNode({
        id: 'test',
        ranges: [[0, 1], [0, 255]],
      });
      expect(node.id).toBe('test');
    });

    it('should throw for empty ranges', () => {
      expect(() => new RangeMapNode({ id: 'test', ranges: [] })).toThrow(
        'at least one range'
      );
    });

    it('should throw for invalid range (max <= min)', () => {
      expect(() => new RangeMapNode({ id: 'test', ranges: [[1, 0]] })).toThrow(
        'must be greater than min'
      );
      expect(() => new RangeMapNode({ id: 'test', ranges: [[5, 5]] })).toThrow(
        'must be greater than min'
      );
    });
  });

  describe('pull', () => {
    it('should remap values from source range to [0, 1]', async () => {
      const node = new RangeMapNode({
        id: 'test',
        ranges: [[0, 100], [0, 255]],
      });

      // Simulate input
      const inputPort = node.inputs.get('input') as InputPort;
      const frame = createFrame([50, 127.5, 100, 255], 2);
      setInputFrame(inputPort, frame);

      // Pull
      await node.pull({ tick: 0, t: 0, dt: 0.033, wallTime: 0 });

      // Check output
      const outputPort = node.outputs.get('out') as OutputPort;
      const outFrame = getOutputFrame(outputPort);
      expect(outFrame).not.toBeNull();

      const payload = outFrame!.payload as MatrixPayload;
      expect(payload.get(0, 0)).toBeCloseTo(0.5, 5); // 50/100
      expect(payload.get(0, 1)).toBeCloseTo(0.5, 5); // 127.5/255
      expect(payload.get(1, 0)).toBeCloseTo(1.0, 5); // 100/100
      expect(payload.get(1, 1)).toBeCloseTo(1.0, 5); // 255/255
    });

    it('should clamp values by default', async () => {
      const node = new RangeMapNode({
        id: 'test',
        ranges: [[0, 100]],
        clamp: true,
      });

      const inputPort = node.inputs.get('input') as InputPort;
      const frame = createFrame([-50, 150], 1);
      setInputFrame(inputPort, frame);

      await node.pull({ tick: 0, t: 0, dt: 0.033, wallTime: 0 });

      const outputPort = node.outputs.get('out') as OutputPort;
      const outFrame = getOutputFrame(outputPort);
      const payload = outFrame!.payload as MatrixPayload;

      expect(payload.get(0)).toBeCloseTo(0.0, 5); // Clamped to 0
      expect(payload.get(1)).toBeCloseTo(1.0, 5); // Clamped to 100, then /100
    });

    it('should not clamp when disabled', async () => {
      const node = new RangeMapNode({
        id: 'test',
        ranges: [[0, 100]],
        clamp: false,
      });

      const inputPort = node.inputs.get('input') as InputPort;
      const frame = createFrame([-50, 150], 1);
      setInputFrame(inputPort, frame);

      await node.pull({ tick: 0, t: 0, dt: 0.033, wallTime: 0 });

      const outputPort = node.outputs.get('out') as OutputPort;
      const outFrame = getOutputFrame(outputPort);
      const payload = outFrame!.payload as MatrixPayload;

      expect(payload.get(0)).toBeCloseTo(-0.5, 5); // -50/100
      expect(payload.get(1)).toBeCloseTo(1.5, 5); // 150/100
    });
  });
});
