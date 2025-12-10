"""DDP (Distributed Display Protocol) package.

This package provides the DDP protocol implementation for sending
RGB pixel data to LED controllers over UDP.

Components:
    - DDPClient: Low-level UDP client for DDP packets
    - DdpSinkNode: Sink node for graph integration

Example config:
    rasl {
        node DdpSink leds {
            target "192.168.1.100";
            fps 30hz;
        }
    }
"""

from .client import DDPClient
from .sink import DdpSinkNode

__all__ = ["DDPClient", "DdpSinkNode"]
