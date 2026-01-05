/**
 * Tests for LiteralNode.
 */

import { describe, it, expect } from 'vitest';
import { LiteralNode } from './literal.js';
import { MatrixPayload, OutputPort } from '../../runtime/index.js';

function getOutputFrame(port: OutputPort | null) {
  if (port) {
    return port._consume();
  }
  return null;
}

describe('LiteralNode', () => {
  describe('construction', () => {
    it('should create with flat array', () => {
      const node = new LiteralNode({
        id: 'test',
        value: [1, 2, 3],
      });
      expect(node.id).toBe('test');
    });

    it('should create with nested array', () => {
      const node = new LiteralNode({
        id: 'test',
        value: [[1, 2, 3], [4, 5, 6]],
      });
      expect(node.id).toBe('test');
    });

    it('should throw for empty value', () => {
      expect(() => new LiteralNode({ id: 'test', value: [] })).toThrow('cannot be empty');
    });
  });

  describe('pull', () => {
    it('should output constant flat array', async () => {
      const node = new LiteralNode({
        id: 'test',
        value: [1, 2, 3],
      });

      await node.pull({ tick: 0, t: 0, dt: 0.033, wallTime: 0 });

      const outputPort = node.outputs.get('out') as OutputPort;
      const frame = getOutputFrame(outputPort);
      expect(frame).not.toBeNull();

      const payload = frame!.payload as MatrixPayload;
      expect(payload.count).toBe(3);
      expect(payload.channels).toBe(1);
      expect(payload.get(0)).toBe(1);
      expect(payload.get(1)).toBe(2);
      expect(payload.get(2)).toBe(3);
    });

    it('should output constant nested array', async () => {
      const node = new LiteralNode({
        id: 'test',
        value: [[1, 2, 3], [4, 5, 6]],
      });

      await node.pull({ tick: 0, t: 0, dt: 0.033, wallTime: 0 });

      const outputPort = node.outputs.get('out') as OutputPort;
      const frame = getOutputFrame(outputPort);
      expect(frame).not.toBeNull();

      const payload = frame!.payload as MatrixPayload;
      expect(payload.count).toBe(2);
      expect(payload.channels).toBe(3);
      expect(payload.get(0, 0)).toBe(1);
      expect(payload.get(0, 1)).toBe(2);
      expect(payload.get(0, 2)).toBe(3);
      expect(payload.get(1, 0)).toBe(4);
      expect(payload.get(1, 1)).toBe(5);
      expect(payload.get(1, 2)).toBe(6);
    });

    it('should return same payload on multiple pulls', async () => {
      const node = new LiteralNode({
        id: 'test',
        value: [42],
      });

      await node.pull({ tick: 0, t: 0, dt: 0.033, wallTime: 0 });
      const outputPort = node.outputs.get('out') as OutputPort;
      const frame1 = getOutputFrame(outputPort);

      await node.pull({ tick: 1, t: 0.033, dt: 0.033, wallTime: 0.033 });
      const frame2 = getOutputFrame(outputPort);

      // Payloads should be the same instance
      expect(frame1!.payload).toBe(frame2!.payload);
    });
  });
});
