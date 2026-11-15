"""RASL - Real-time Async Streaming for Lighting.

RASL is a Python-based data engine for processing and routing
DMX/sACN lighting data through a configurable DAG (Directed Acyclic Graph).

Packages, each importing only from those below it in this list:
    - app: the rasl command, the web API and dashboard
    - config: the config language; builds and reloads plans (load_config)
    - runtime: runs a plan (Runtime)
    - nodes: built-in nodes; devices: protocol packages (sACN, DDP, LIFX, Govee)
    - graph: nodes' contract, ports, edges, GraphBuilder, ExecutionPlan
    - color: color models, conversions and payloads
    - signal: Frame and payloads
    - units: Duration and Frequency

Example:
    >>> from rasl.config import load_config
    >>> from rasl.runtime import Runtime
    >>> import anyio
    >>>
    >>> plan = load_config("config.conf")
    >>> runtime = Runtime(plan)
    >>> anyio.run(runtime.run)

CLI usage:
    $ rasl config.conf
    $ rasl config.conf --api-port 8080  # With web dashboard
    $ rasl --help
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
