"""RASL CLI - Command line interface for the RASL application.

This module provides the main entry point for the RASL command line tool.
It handles configuration loading, runtime execution, and optional web API server.

CLI usage:
    $ rasl config.conf
    $ rasl config.conf --api-port 8080  # With web dashboard
    $ rasl --help
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path
from typing import Optional

import anyio
import structlog

from rasl import __version__
from rasl.config import load_config
from rasl.engine.graph import ExecutionPlan
from rasl.runtime import UnifiedScheduler

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        # Do not sort keys so field order follows binding / call order
        structlog.dev.ConsoleRenderer(sort_keys=False),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


def _create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="rasl",
        description="RASL - Real-time Async Streaming for Lighting",
    )
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        help="Path to configuration file",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate config and exit without running",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="Print graph structure as JSON and exit",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=None,
        metavar="PORT",
        help="Start web API server on this port (e.g., 8080)",
    )
    parser.add_argument(
        "--api-host",
        type=str,
        default="127.0.0.1",
        metavar="HOST",
        help="Host for web API server (default: 127.0.0.1)",
    )
    return parser


async def _run_with_shutdown(
    scheduler: UnifiedScheduler,
    plan: "ExecutionPlan",
    api_host: Optional[str] = None,
    api_port: Optional[int] = None,
) -> None:
    """Run the scheduler with graceful shutdown handling.

    Sets up signal handlers for SIGINT and SIGTERM to enable
    graceful shutdown. Optionally starts the web API server.

    Args:
        scheduler: The UnifiedScheduler instance to execute.
        plan: The ExecutionPlan for the API server.
        api_host: Host for the API server (if enabled).
        api_port: Port for the API server (if enabled).
    """
    def _signal_handler(signum: int) -> None:
        logger.info("shutdown_signal_received", signal=signal.Signals(signum).name)

    # Register signal handlers
    with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:
        async with anyio.create_task_group() as tg:
            async def _wait_for_signal() -> None:
                async for signum in signals:
                    _signal_handler(signum)
                    tg.cancel_scope.cancel()
                    break

            tg.start_soon(_wait_for_signal)
            tg.start_soon(scheduler.run)
            
            # Start API server if requested
            if api_port is not None:
                from rasl.server import create_app, run_server
                app = create_app(scheduler, plan)
                logger.info("starting_api_server", host=api_host, port=api_port)
                print(f"Dashboard: http://{api_host}:{api_port}/")
                tg.start_soon(run_server, app, api_host, api_port)


def main(args: Optional[list[str]] = None) -> int:
    """Main entry point for the RASL CLI.

    Args:
        args: Command line arguments (uses sys.argv if None).

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    parser = _create_parser()
    parsed = parser.parse_args(args)

    if not parsed.config:
        parser.print_help()
        return 1

    config_path: Path = parsed.config
    if not config_path.exists():
        logger.error("config_not_found", path=str(config_path))
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        logger.info("loading_config", path=str(config_path))
        plan = load_config(config_path)
        logger.info(
            "config_loaded",
            nodes=len(plan.nodes),
            order=plan.topological_order,
        )
    except Exception as e:
        logger.error("config_error", error=str(e))
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1

    if parsed.validate:
        print(f"Config valid: {len(plan.nodes)} nodes, order: {plan.topological_order}")
        return 0

    if parsed.describe:
        description = plan.describe()
        print(json.dumps(description, indent=2))
        return 0

    scheduler = UnifiedScheduler(plan)
    logger.info("starting_scheduler")

    try:
        anyio.run(
            _run_with_shutdown,
            scheduler,
            plan,
            parsed.api_host,
            parsed.api_port,
        )
    except KeyboardInterrupt:
        logger.info("interrupted")
    except Exception as e:
        logger.error("runtime_error", error=str(e))
        print(f"Runtime error: {e}", file=sys.stderr)
        return 1

    logger.info("shutdown_complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
