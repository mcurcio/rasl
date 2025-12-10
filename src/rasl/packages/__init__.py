"""RASL Packages - Protocol extensions and external integrations.

This package contains self-contained protocol implementations that are
not part of the core RASL engine. Each subpackage provides nodes for
a specific protocol or integration.

Available packages:
    - sacn: sACN/E1.31 DMX protocol (source and sink nodes)
    - ddp: Distributed Display Protocol (sink node)

These packages are optional and can be imported independently:

    from rasl.packages.sacn import SacnSourceNode, SacnSinkNode
    from rasl.packages.ddp import DdpSinkNode

All package nodes are also re-exported from rasl.nodes for convenience.
"""

from . import ddp, sacn

__all__ = ["ddp", "sacn"]
