"""RASL - Real-time Async Streaming for Lighting.

RASL is a Python-based data engine for processing and routing
DMX/sACN lighting data through a configurable DAG (Directed Acyclic Graph).

Key components:
    - engine: Core DAG types (Frame, Node, GraphBuilder)
    - nodes: Concrete node implementations (grouped by function)
    - packages: Protocol extensions (sACN, DDP)
    - runtime: Execution scheduler (Runtime)
    - config: Configuration loading (load_config)
    - server: Web API and dashboard

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
