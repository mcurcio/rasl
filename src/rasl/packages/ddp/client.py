"""DDP (Distributed Display Protocol) client implementation.

This module provides DDPClient for sending RGB pixel data to LED
controllers over UDP. DDP is optimized for high pixel counts with
up to 480 RGB pixels per packet.

Protocol reference: http://www.3waylabs.com/ddp/
"""

import socket
import struct
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

DDP_PORT = 4048
DDP_HEADER_LEN = 10

# DDP spec: up to 1440 bytes (480 RGB pixels) per packet is common
DDP_MAX_DATALEN = 1440

# Flags
DDP_VER1 = 0x40      # Version 1
DDP_PUSH = 0x01      # Push flag - display data after this packet

# Real-world compatible data type
DDP_DATATYPE_RGB = 0x00

DDP_DEFAULT_DEST_ID = 0x01  # Default output device ID


class DDPClient:
    """UDP client for sending DDP packets to LED controllers.
    
    DDP (Distributed Display Protocol) is a simple protocol for
    transmitting pixel data over UDP. It supports large pixel counts
    by splitting data across multiple packets.
    
    Example:
        client = DDPClient("192.168.1.100")
        client.connect()
        client.send(pixel_data)  # numpy array of RGB values
        client.close()
    """
    
    def __init__(
        self,
        host: str,
        port: int = DDP_PORT,
        destination_id: int = DDP_DEFAULT_DEST_ID,
    ) -> None:
        self.host = host
        self.port = port
        self.destination_id = destination_id
        self._sock: socket.socket | None = None
        self._sequence = 0

    def connect(self, *, blocking: bool = True) -> None:
        """Open UDP socket for sending packets."""
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setblocking(bool(blocking))

    def close(self) -> None:
        """Close the UDP socket."""
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def send(self, data: ArrayLike) -> None:
        """Send pixel data as DDP packets.
        
        Args:
            data: Pixel data as numpy array. Float values are scaled
                  from [0, 1] to [0, 255]. Integer values are used directly.
        
        Raises:
            RuntimeError: If client is not connected.
        """
        if self._sock is None:
            raise RuntimeError("DDPClient not connected. Call connect() first.")

        arr = np.asarray(data)

        if np.issubdtype(arr.dtype, np.floating):
            byte_data = (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)
        elif arr.dtype == np.uint8:
            # Fast path: already quantized.
            byte_data = arr
        else:
            byte_data = arr.astype(np.uint8)

        # Ensure contiguous 1D buffer (so slicing produces cheap views and
        # sendmsg can transmit without intermediate copies).
        byte_data = np.ascontiguousarray(byte_data).ravel()
        total_len = len(byte_data)
        if total_len == 0:
            return

        num_packets = (total_len + DDP_MAX_DATALEN - 1) // DDP_MAX_DATALEN

        can_sendmsg = hasattr(self._sock, "sendmsg")

        for i in range(num_packets):
            byte_offset = i * DDP_MAX_DATALEN
            chunk = byte_data[byte_offset : byte_offset + DDP_MAX_DATALEN]
            is_last = (i == num_packets - 1)
            self._sequence = (self._sequence % 15) + 1

            # Avoid copying chunk to bytes when possible.
            view = memoryview(chunk)
            self._send_packet(self._sequence, byte_offset, view, is_last, can_sendmsg)

    def send_nonblocking(
        self,
        byte_data: ArrayLike,
        *,
        start_offset: int = 0,
        push_every_packet: bool = False,
    ) -> int:
        """Send as many packets as possible without blocking.

        Returns the next byte offset to resume from. Returns 0 when complete.

        This method assumes the socket is non-blocking (connect(blocking=False)).
        If the kernel send buffer is full, it returns without raising.
        """
        if self._sock is None:
            raise RuntimeError("DDPClient not connected. Call connect() first.")

        arr = np.asarray(byte_data)
        if arr.dtype != np.uint8:
            arr = arr.astype(np.uint8)
        arr = np.ascontiguousarray(arr).ravel()
        total_len = int(arr.size)
        if total_len == 0:
            return 0

        offset = max(0, int(start_offset))
        if offset >= total_len:
            return 0

        can_sendmsg = hasattr(self._sock, "sendmsg")

        while offset < total_len:
            chunk = arr[offset : offset + DDP_MAX_DATALEN]
            is_last = (offset + int(chunk.size)) >= total_len
            self._sequence = (self._sequence % 15) + 1

            view = memoryview(chunk)

            try:
                self._send_packet(
                    self._sequence,
                    offset,
                    view,
                    is_last,
                    can_sendmsg,
                    push_every_packet=push_every_packet,
                )
            except (BlockingIOError, InterruptedError):
                return offset
            except OSError as e:
                if getattr(e, "errno", None) in {11, 35, 10035}:
                    return offset
                raise

            offset += int(chunk.size)

        return 0

    def _send_packet(
        self,
        sequence: int,
        byte_offset: int,
        data: memoryview,
        is_last: bool,
        can_sendmsg: bool,
        *,
        push_every_packet: bool = False,
    ) -> None:
        """Send a single DDP packet."""
        if self._sock is None:
            return

        flags = DDP_VER1 | (DDP_PUSH if (push_every_packet or is_last) else 0)
        data_len = len(data)

        header = struct.pack(
            "!BBBBLH",
            flags,
            sequence & 0x0F,
            DDP_DATATYPE_RGB,
            self.destination_id,
            byte_offset,
            data_len,
        )

        # On platforms that support it, sendmsg lets us avoid concatenating
        # header+payload into a new bytes object.
        if can_sendmsg:
            self._sock.sendmsg([header, data], [], 0, (self.host, self.port))
        else:
            # Fallback: concatenate (copy) to send via sendto.
            self._sock.sendto(header + data.tobytes(), (self.host, self.port))
