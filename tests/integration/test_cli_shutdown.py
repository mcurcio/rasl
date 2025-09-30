"""
Integration tests for CLI graceful shutdown behavior.

Tests that the CLI responds properly to SIGINT (Ctrl+C) and shuts down gracefully.
"""

import pytest
import subprocess
import signal
import time
import os
import threading
from pathlib import Path


class TestCLIShutdown:
    """Test CLI shutdown behavior."""
    
    def test_cli_responds_to_sigint(self):
        """
        Test that the CLI responds to SIGINT and shuts down gracefully.
        
        Uses shell-based approach to avoid subprocess blocking issues.
        """
        script_path = Path("examples/simple_sine.py")
        pid_file = f"/tmp/rasl_test_{os.getpid()}.pid"
        
        try:
            # Start the process in background using shell command
            cmd = f"cd {os.getcwd()} && source .venv/bin/activate && python -m rasl run {script_path} & echo $! > {pid_file}"
            
            exit_code = os.system(cmd)
            if exit_code != 0:
                pytest.fail(f"Failed to start process: exit code {exit_code}")
            
            # Wait for PID file
            time.sleep(0.5)
            if not os.path.exists(pid_file):
                pytest.fail("PID file not created")
            
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Wait for startup
            time.sleep(2.0)
            
            # Check if process is running
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pytest.fail("Process died during startup")
            
            # Send SIGINT to process group (like Ctrl+C)
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGINT)
            
            # Wait for graceful shutdown
            for i in range(50):  # Wait up to 5 seconds
                try:
                    os.kill(pid, 0)
                    time.sleep(0.1)
                except ProcessLookupError:
                    # Process terminated - success!
                    return
            
            # If we get here, process didn't terminate
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            pytest.fail("Process did not respond to SIGINT within 5 seconds")
            
        finally:
            # Cleanup
            try:
                os.unlink(pid_file)
            except FileNotFoundError:
                pass
            # Kill any remaining processes
            os.system("pkill -f 'python -m rasl' 2>/dev/null")
    
    def test_signal_handler_registration(self):
        """
        Test that signal handlers are properly registered in the RASLApp.
        
        This is a unit test that verifies the signal handling setup
        without actually running the full CLI.
        """
        from rasl.app import RASLApp
        from rasl.config import Config
        from pathlib import Path
        
        config = Config(
            script_path=Path("examples/simple_sine.py"),
            ui_port=8080,
            api_port=8081
        )
        
        app = RASLApp(config)
        
        # This should not raise an exception
        app._setup_signal_handlers()
        
        # Verify shutdown event exists and is not set
        assert hasattr(app, '_shutdown_event'), "App should have shutdown event"
        assert not app._shutdown_event.is_set(), "Shutdown event should not be set initially"
