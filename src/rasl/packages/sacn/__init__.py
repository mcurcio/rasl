"""sACN/E1.31 (Streaming ACN) package.

This package provides sACN protocol implementation for sending and
receiving DMX data over network multicast/unicast.

Components:
    - SacnSourceNode: Source node that receives sACN DMX packets
    - SacnSinkNode: Sink node that transmits sACN DMX packets
    - shims: Compatibility patches for the sacn library

Example config:
    rasl {
        node SacnSource dmx_in {
            universes 1 2 3;
            bind_address "0.0.0.0";
        }
        
        node SacnSink dmx_out {
            target_host "10.0.60.30";
            target_universe 1;
        }
    }
"""

from .sink import SacnSinkNode
from .source import SacnSourceNode

__all__ = ["SacnSourceNode", "SacnSinkNode"]
