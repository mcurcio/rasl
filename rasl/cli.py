"""
Command line interface for RASL application.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel

from .app import RASLApp
from .config import Config

console = Console()


@click.group()
@click.version_option()
def cli():
    """RASL - Real-Time Animation Show Library"""
    pass


@cli.command()
@click.argument("script", type=click.Path(exists=True, path_type=Path))
@click.option("--ui-port", default=8080, help="Web UI port")
@click.option("--api-port", default=8081, help="API server port")
@click.option("--host", default="localhost", help="Server host")
@click.option("--watch/--no-watch", default=True, help="Watch script for changes")
@click.option("--debug/--no-debug", default=False, help="Enable debug mode")
def run(
    script: Path,
    ui_port: int,
    api_port: int,
    host: str,
    watch: bool,
    debug: bool,
):
    """Run a RASL script with built-in web UI."""
    
    config = Config(
        script_path=script,
        ui_port=ui_port,
        api_port=api_port,
        host=host,
        watch_enabled=watch,
        debug_mode=debug,
    )
    
    console.print(Panel.fit(
        f"🎭 Starting RASL Application\\n"
        f"Script: {script}\\n"
        f"Web UI: http://{host}:{ui_port}\\n"
        f"API: http://{host}:{api_port}\\n"
        f"Watch: {'Enabled' if watch else 'Disabled'}",
        title="RASL",
        border_style="bright_blue"
    ))
    
    app = RASLApp(config)
    
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        console.print("\\n👋 Shutting down RASL...")
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.argument("script", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", help="Output file for validation report")
def validate(script: Path, output: Optional[str]):
    """Validate a RASL script without running it."""
    
    console.print(f"🔍 Validating {script}...")
    
    # TODO: Implement script validation
    # This should load the script, build the graph, and run all validation
    # without actually starting the execution engine
    
    console.print("✅ Script validation complete", style="green")


@cli.command()
@click.argument("script", type=click.Path(exists=True, path_type=Path))
@click.option("--format", type=click.Choice(["json", "yaml", "png", "svg"]), default="json")
@click.option("--output", "-o", required=True, help="Output file path")
def export(script: Path, format: str, output: str):
    """Export graph representation from a RASL script."""
    
    console.print(f"📤 Exporting {script} as {format}...")
    
    # TODO: Implement graph export
    # Load script, build graph, serialize to requested format
    
    console.print(f"✅ Exported to {output}", style="green")


@cli.command()
def examples():
    """List available example scripts."""
    
    examples_dir = Path(__file__).parent.parent / "examples"
    
    if not examples_dir.exists():
        console.print("No examples directory found", style="yellow")
        return
    
    console.print("📚 Available Examples:", style="bold")
    
    for example in examples_dir.glob("*.py"):
        console.print(f"  • {example.name}")
    
    console.print(f"\\nRun an example with: rasl run examples/<name>.py")


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
