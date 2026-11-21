"""sACN/E1.31 (Streaming ACN) package.

- ``SacnUniverseNode`` (``SacnUniverse``): one sACN universe; receives it when an
  output is wired
- ``SacnSinkNode`` (``SacnSink``): sends one universe (until SacnUniverse sends)
- ``protocol``: the E1.31 codec, sequence rule and source arbitration (pure)
- ``transport``: the receiver SacnUniverse nodes share through ``NodeContext.resources``
- ``shims``: the sacn library patch SacnSink needs for universe 0

Example config:
    graph {
        node SacnUniverse dmx_in { universe 1; channels 510; }
        node Reshape pixels { components 3; connect dmx_in; }
        node SacnSink dmx_out {
            target_host "10.0.60.30";
            target_universe 1;
            connect pixels;
        }
    }
"""

from rasl.devices.sacn.sink import SacnSinkNode
from rasl.devices.sacn.universe import SacnUniverseNode

__all__ = ["SacnSinkNode", "SacnUniverseNode"]
