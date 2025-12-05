"""RASL Nodes - Concrete node implementations for the processing graph.

This package provides the built-in node types for common operations:

Source Nodes:
    - SacnSourceNode: Receive sACN/E1.31 DMX data from network
    - SineSourceNode: Generate virtual sine-wave test data

Transform Nodes:
    - UniversePatchTransform: Remap DMX channels between universes
    - Segment: Channel mapping definition for UniversePatchTransform

Sink Nodes:
    - SacnSinkNode: Transmit sACN/E1.31 DMX data to network
    - ConsoleSinkNode: Log frames to the console/logger

Nodes are normally constructed by the configuration loader, which parses
nginx-style config into :class:`~rasl.engine.node_config.NodeConfig`
instances and then instantiates the corresponding node classes.

Example configuration (see ``sample.conf``)::

    rasl {
        node SacnSource sacnSource {
            universes 1 2;
            metadata "colorSpace=rgb";
        }
        node UniversePatch universePatch0 {
            output universe0;
            segment { source_universe 1; source_channel 1; length 150; target_channel 1; }
        }
        node SacnSink sacnSink0 {
            input universe0;
            target_host "10.0.60.30";
            target_universe 0;
        }
    }
"""

from .console_sink import ConsoleSinkNode
from .sacn_sink import SacnSinkNode
from .sacn_source import SacnSourceNode
from .sine_source import SineSourceNode
from .universe_patch import Segment, UniversePatchTransform

__all__ = [
    "ConsoleSinkNode",
    "SacnSinkNode",
    "SacnSourceNode",
    "Segment",
    "SineSourceNode",
    "UniversePatchTransform",
]
