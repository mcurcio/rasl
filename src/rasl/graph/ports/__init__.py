"""Ports: how a node declares what it reads and writes, and the objects it
reads and writes through.

A node class declares ``inputs`` and ``outputs`` as ``PortGroup``s of specs;
during a pull it reads ``self.inputs.<name>.read()`` and writes
``self.outputs.<name>.write(frame)``.
"""

from rasl.graph.ports.group import EMPTY_PORTS, BoundPortGroup, PortGroup
from rasl.graph.ports.port import InputPort, OutputPort
from rasl.graph.ports.spec import AcceptsSpec, CountSpec, InputPortSpec, OutputPortSpec, ProducesSpec

__all__ = [
    "EMPTY_PORTS",
    "AcceptsSpec",
    "BoundPortGroup",
    "CountSpec",
    "InputPort",
    "InputPortSpec",
    "OutputPort",
    "OutputPortSpec",
    "PortGroup",
    "ProducesSpec",
]
