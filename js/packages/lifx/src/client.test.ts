import { describe, it, expect } from 'vitest';
import {
  LifxLanClient,
  parseTargetList,
  hsbkToLifx,
  LIFX_DEFAULT_PORT,
} from './client.js';

describe('parseTargetList', () => {
  it('should parse single IP', () => {
    const endpoints = parseTargetList('192.168.1.100');
    expect(endpoints).toHaveLength(1);
    expect(endpoints[0].ip).toBe('192.168.1.100');
    expect(endpoints[0].port).toBe(LIFX_DEFAULT_PORT);
    expect(endpoints[0].mac).toBeUndefined();
  });

  it('should parse IP with port', () => {
    const endpoints = parseTargetList('192.168.1.100:12345');
    expect(endpoints).toHaveLength(1);
    expect(endpoints[0].ip).toBe('192.168.1.100');
    expect(endpoints[0].port).toBe(12345);
  });

  it('should parse multiple IPs', () => {
    const endpoints = parseTargetList('192.168.1.100, 192.168.1.101, 192.168.1.102');
    expect(endpoints).toHaveLength(3);
    expect(endpoints[0].ip).toBe('192.168.1.100');
    expect(endpoints[1].ip).toBe('192.168.1.101');
    expect(endpoints[2].ip).toBe('192.168.1.102');
  });

  it('should parse MAC@IP format', () => {
    const endpoints = parseTargetList('d0:73:d5:12:34:56@192.168.1.100');
    expect(endpoints).toHaveLength(1);
    expect(endpoints[0].ip).toBe('192.168.1.100');
    expect(endpoints[0].mac).toBeDefined();
    expect(endpoints[0].mac).toEqual(new Uint8Array([0xd0, 0x73, 0xd5, 0x12, 0x34, 0x56]));
  });

  it('should parse MAC@IP:port format', () => {
    const endpoints = parseTargetList('d073d5123456@192.168.1.100:9999');
    expect(endpoints).toHaveLength(1);
    expect(endpoints[0].ip).toBe('192.168.1.100');
    expect(endpoints[0].port).toBe(9999);
    expect(endpoints[0].mac).toEqual(new Uint8Array([0xd0, 0x73, 0xd5, 0x12, 0x34, 0x56]));
  });

  it('should handle empty string', () => {
    const endpoints = parseTargetList('');
    expect(endpoints).toHaveLength(0);
  });

  it('should handle whitespace-only entries', () => {
    const endpoints = parseTargetList('192.168.1.100, , 192.168.1.101');
    expect(endpoints).toHaveLength(2);
  });

  it('should parse IPv6 literal', () => {
    const endpoints = parseTargetList('[::1]:56700');
    expect(endpoints).toHaveLength(1);
    expect(endpoints[0].ip).toBe('::1');
    expect(endpoints[0].port).toBe(56700);
  });

  it('should throw on invalid MAC', () => {
    expect(() => parseTargetList('invalid@192.168.1.100')).toThrow('invalid MAC');
  });

  it('should throw on empty host', () => {
    expect(() => parseTargetList(':56700')).toThrow('invalid host');
  });
});

describe('hsbkToLifx', () => {
  it('should convert normalized values to LIFX integers', () => {
    const result = hsbkToLifx(0.5, 1.0, 0.75, 0.5);
    expect(result.hue).toBe(32768); // 0.5 * 65535
    expect(result.saturation).toBe(65535); // 1.0 * 65535
    expect(result.brightness).toBe(49151); // 0.75 * 65535
    expect(result.kelvin).toBe(5250); // 0.5 * 7500 + 1500
  });

  it('should clamp values to [0,1]', () => {
    const result = hsbkToLifx(-0.5, 1.5, 0.5, 0.5);
    expect(result.hue).toBe(0);
    expect(result.saturation).toBe(65535);
  });

  it('should handle hue at max', () => {
    const result = hsbkToLifx(1.0, 0.5, 0.5, 0.5);
    // 1.0 * 65535 = 65535, which is valid (wraps to 0 only at 65536)
    expect(result.hue).toBe(65535);
  });

  it('should clamp kelvin to valid range', () => {
    const minResult = hsbkToLifx(0, 0, 0, 0);
    expect(minResult.kelvin).toBe(1500);

    const maxResult = hsbkToLifx(0, 0, 0, 1);
    expect(maxResult.kelvin).toBe(9000);
  });
});

describe('LifxLanClient', () => {
  it('should create with endpoint', () => {
    const client = new LifxLanClient({ ip: '192.168.1.100', port: 56700 });
    expect(client.endpoint.ip).toBe('192.168.1.100');
    expect(client.endpoint.port).toBe(56700);
  });

  it('should describe endpoint', () => {
    const client = new LifxLanClient({
      ip: '192.168.1.100',
      port: 56700,
      mac: new Uint8Array([0xd0, 0x73, 0xd5, 0x12, 0x34, 0x56]),
    });
    const desc = client.describe();
    expect(desc.ip).toBe('192.168.1.100');
    expect(desc.port).toBe(56700);
    expect(desc.mac).toBe('d073d5123456');
  });

  it('should describe endpoint without MAC', () => {
    const client = new LifxLanClient({ ip: '192.168.1.100', port: 56700 });
    const desc = client.describe();
    expect(desc.mac).toBeNull();
  });

  it('should throw if sendSetColor called before start', () => {
    const client = new LifxLanClient({ ip: '192.168.1.100', port: 56700 });
    expect(() => client.sendSetColor(0, 0, 0, 3500, 0, false)).toThrow('has not been started');
  });

  it('should be safe to call stop multiple times', () => {
    const client = new LifxLanClient({ ip: '192.168.1.100', port: 56700 });
    client.stop();
    client.stop();
    // Should not throw
  });
});
