"""sACN/E1.31 (Streaming ACN) package.

- ``SacnUniverseNode`` (``SacnUniverse``): one sACN universe; sends it when its ``dmx``
  input is wired and receives it when an output is
- ``protocol``: the E1.31 codec, sequence rule and source arbitration (pure)
- ``transport``: the receiver, sender and per-universe outputs SacnUniverse nodes share
  through ``NodeContext.resources``

Example config:
    graph {
        node SacnUniverse dmx_in { universe 1; channels 510; }
        node Reshape pixels { components 3; connect dmx_in; }
        node SacnUniverse dmx_out { universe 2; target "10.0.60.30"; connect pixels; }
    }
"""

from rasl.devices.sacn.universe import SacnUniverseNode

__all__ = ["SacnUniverseNode"]
