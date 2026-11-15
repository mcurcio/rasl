"""RASL Packages - Protocol extensions and external integrations.

This package contains self-contained protocol implementations that are
not part of the core RASL engine. Each subpackage provides nodes for
a specific protocol or integration.

Available packages:
    - sacn: sACN/E1.31 DMX protocol (source and sink nodes)
    - ddp: Distributed Display Protocol (sink node)
    - govee: Govee LAN protocol (sink node)
    - lifx: LIFX LAN protocol (sink node)

These packages are optional and can be imported independently:

    from rasl.packages.sacn import SacnSourceNode, SacnSinkNode
    from rasl.packages.ddp import DdpSinkNode

The registry imports this package as the "rasl.nodes" entry point named
"devices", which registers every node below.
"""

from rasl.packages import ddp, govee, lifx, sacn

__all__ = ["ddp", "govee", "lifx", "sacn"]
