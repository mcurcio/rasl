#!/usr/bin/env python3
"""Test script for DDP protocol implementation.

Usage:
    uv run python scripts/test_ddp.py <host> [num_pixels]

Example:
    uv run python scripts/test_ddp.py 10.0.60.30 100
"""

import argparse
import socket
import struct
import sys
import time

import numpy as np


def send_ddp_packet(
    sock: socket.socket,
    host: str,
    port: int,
    data: bytes,
    offset: int,
    sequence: int,
    is_last: bool,
) -> None:
    """Send a single DDP packet."""
    VER1 = 0x40
    PUSH = 0x01
    DATATYPE = 0x0B  # RGB 8-bit
    DEST_ID = 1

    flags = VER1 | (PUSH if is_last else 0)
    header = struct.pack(
        "!BBBBLH",
        flags,
        sequence,
        DATATYPE,
        DEST_ID,
        offset,
        len(data),
    )
    sock.sendto(header + data, (host, port))


def send_color(sock: socket.socket, host: str, num_pixels: int, r: int, g: int, b: int, seq: int) -> None:
    """Send a solid color to all pixels."""
    data = bytes([r, g, b] * num_pixels)
    
    # Send in chunks of 1350 bytes (450 pixels)
    MAX_CHUNK = 1350
    total_len = len(data)
    offset = 0
    
    while offset < total_len:
        chunk_size = min(MAX_CHUNK, total_len - offset)
        chunk = data[offset:offset + chunk_size]
        is_last = (offset + chunk_size >= total_len)
        send_ddp_packet(sock, host, 4048, chunk, offset, seq, is_last)
        offset += chunk_size


def main():
    parser = argparse.ArgumentParser(description="Test DDP protocol")
    parser.add_argument("host", help="Target IP address")
    parser.add_argument("num_pixels", type=int, nargs="?", default=100, help="Number of pixels (default: 100)")
    args = parser.parse_args()

    host = args.host
    num_pixels = args.num_pixels
    port = 4048

    print(f"Testing DDP to {host}:{port} with {num_pixels} pixels")
    print()

    # Create socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(True)

    try:
        # Test sequence
        colors = [
            ("Red", 255, 0, 0),
            ("Green", 0, 255, 0),
            ("Blue", 0, 0, 255),
            ("White", 255, 255, 255),
            ("Yellow", 255, 255, 0),
            ("Cyan", 0, 255, 255),
            ("Magenta", 255, 0, 255),
            ("Off", 0, 0, 0),
        ]

        for i, (name, r, g, b) in enumerate(colors):
            print(f"Sending {name}...")
            send_color(sock, host, num_pixels, r, g, b, (i % 15) + 1)
            time.sleep(1)

        print()
        print("Test complete!")
        print()
        print("If the LEDs did not change color, check:")
        print("  1. The device is powered on and connected to the network")
        print("  2. The IP address is correct")
        print("  3. The device is configured for DDP mode (WLED: Sync Settings -> Realtime -> DDP)")
        print("  4. The device has been rebooted after changing to DDP mode")

    finally:
        sock.close()


if __name__ == "__main__":
    main()
