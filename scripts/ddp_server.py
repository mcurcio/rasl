#!/usr/bin/env python3
"""DDP server for debugging - listens for and logs incoming DDP packets.

Usage:
    uv run python scripts/ddp_server.py [--port 4048] [--bind 0.0.0.0]
"""

import argparse
import socket
import struct
from datetime import datetime


DDP_PORT = 4048
DDP_HEADER_LEN = 10

# Flag bits
DDP_VER_MASK = 0xC0
DDP_VER1 = 0x40
DDP_PUSH = 0x01
DDP_QUERY = 0x02
DDP_REPLY = 0x04
DDP_STORAGE = 0x08
DDP_TIMECODE = 0x10


def parse_flags(flags: int) -> list[str]:
    """Parse DDP flags byte into human-readable list."""
    parts = []
    ver = (flags & DDP_VER_MASK) >> 6
    parts.append(f"ver={ver}")
    if flags & DDP_PUSH:
        parts.append("PUSH")
    if flags & DDP_QUERY:
        parts.append("QUERY")
    if flags & DDP_REPLY:
        parts.append("REPLY")
    if flags & DDP_STORAGE:
        parts.append("STORAGE")
    if flags & DDP_TIMECODE:
        parts.append("TIMECODE")
    return parts


def parse_datatype(dt: int) -> str:
    """Parse DDP data type byte."""
    # Common values
    if dt == 0x01:
        return "RGB24"
    if dt == 0x0B:
        return "RGB8(type=1,size=3)"
    
    # Generic parsing
    dtype = (dt >> 3) & 0x07
    size = dt & 0x07
    
    type_names = {0: "undefined", 1: "RGB", 2: "HSL", 3: "RGBW", 4: "Grayscale"}
    size_names = {0: "1bit", 1: "4bit", 2: "8bit", 3: "16bit", 4: "24bit", 5: "32bit"}
    
    return f"{type_names.get(dtype, f'type{dtype}')}/{size_names.get(size, f'size{size}')}"


def run_server(bind_addr: str, port: int, verbose: bool = False):
    """Run DDP server and log incoming packets."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_addr, port))
    
    print(f"DDP Server listening on {bind_addr}:{port}")
    print("Press Ctrl+C to stop\n")
    print("-" * 80)
    
    packet_count = 0
    
    try:
        while True:
            data, addr = sock.recvfrom(65535)
            packet_count += 1
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            if len(data) < DDP_HEADER_LEN:
                print(f"[{timestamp}] #{packet_count} from {addr}: Too short ({len(data)} bytes)")
                continue
            
            # Parse header
            flags, seq, datatype, dest_id, offset, length = struct.unpack(
                "!BBBBLH", data[:DDP_HEADER_LEN]
            )
            
            payload = data[DDP_HEADER_LEN:]
            
            flag_str = " ".join(parse_flags(flags))
            dtype_str = parse_datatype(datatype)
            
            print(f"[{timestamp}] #{packet_count} from {addr[0]}:{addr[1]}")
            print(f"  Header: flags=0x{flags:02X} ({flag_str}) seq={seq} type=0x{datatype:02X} ({dtype_str})")
            print(f"          dest_id={dest_id} offset={offset} length={length}")
            print(f"  Payload: {len(payload)} bytes (header says {length})")
            
            if verbose and len(payload) > 0:
                # Show first few RGB values
                num_pixels = min(8, len(payload) // 3)
                if num_pixels > 0:
                    pixels = []
                    for i in range(num_pixels):
                        r, g, b = payload[i*3], payload[i*3+1], payload[i*3+2]
                        pixels.append(f"({r},{g},{b})")
                    print(f"  First {num_pixels} pixels: {' '.join(pixels)}")
                
                # Show hex dump of first 32 bytes
                hex_bytes = ' '.join(f'{b:02X}' for b in payload[:32])
                print(f"  Hex: {hex_bytes}{'...' if len(payload) > 32 else ''}")
            
            print()
            
    except KeyboardInterrupt:
        print(f"\nReceived {packet_count} packets total")
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description="DDP packet receiver/logger")
    parser.add_argument("--port", "-p", type=int, default=DDP_PORT, help="Port to listen on")
    parser.add_argument("--bind", "-b", default="0.0.0.0", help="Address to bind to")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show pixel data")
    args = parser.parse_args()
    
    run_server(args.bind, args.port, args.verbose)


if __name__ == "__main__":
    main()
