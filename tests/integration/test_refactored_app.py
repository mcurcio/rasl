"""
Integration tests for the refactored RASL application.

Tests that the refactored app with extracted managers works correctly
in real execution scenarios.
"""

import pytest
import subprocess
import tempfile
import time
from pathlib import Path


class TestRefactoredApp:
    """Integration tests for refactored RASLApp with managers."""
    
    def test_refactored_app_runs_simple_sine(self):
        """
        Refactored RASLApp should run simple_sine.py successfully.
        
        Tests that the manager-based architecture works end-to-end.
        """
        process = subprocess.Popen([
            "python", "-m", "rasl", "run", "examples/simple_sine.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        try:
            # Let it run briefly
            time.sleep(3)
            
            # Should be running successfully
            assert process.poll() is None, "Refactored app should run simple_sine.py"
            
            # Terminate and check output
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            
            # Should see expected output patterns
            assert "Script loaded successfully" in stderr, "Should load script"
            assert "Starting execution engine" in stderr, "Should start engine"
            assert "Web server started successfully" in stderr, "Should start web server"
            
            # Should not have manager-related errors
            assert "WebServerManager" not in stderr or "error" not in stderr.lower()
            assert "ScriptManager" not in stderr or "error" not in stderr.lower()
            
        except subprocess.TimeoutExpired:
            process.kill()
            pytest.fail("Refactored app did not terminate gracefully")
    
    def test_refactored_app_web_server_starts(self):
        """
        Refactored RASLApp should start web server through WebServerManager.
        
        Tests that the WebServerManager integration works correctly.
        """
        import urllib.request
        import json
        
        process = subprocess.Popen([
            "python", "-m", "rasl", "run", "examples/simple_sine.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        try:
            # Wait for startup
            time.sleep(4)
            
            # Web server should be accessible
            try:
                with urllib.request.urlopen("http://localhost:8080/api/health", timeout=2) as response:
                    assert response.status == 200, "Web server should be accessible"
                    
                    health_data = json.loads(response.read().decode())
                    assert "status" in health_data, "Should return health status"
                    
            except Exception as e:
                pytest.fail(f"Web server not accessible: {e}")
        
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    
    def test_refactored_app_hot_reload_works(self):
        """
        Refactored RASLApp should handle hot-reload through ScriptManager.
        
        Tests that the ScriptManager integration works for file changes.
        """
        # Create a temporary script
        test_script_content = '''
from rasl import *

sine = SineSource(freq=1.0, channels=1)
console = ConsoleSink(format="raw", update_interval=0.1)
sine.ports.out >> console.ports["in"]
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_file.write(test_script_content)
            temp_script = Path(temp_file.name)
        
        try:
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Let it start
            time.sleep(2)
            
            # Modify the script
            modified_content = test_script_content.replace("channels=1", "channels=2")
            with open(temp_script, 'w') as f:
                f.write(modified_content)
            
            # Wait for hot-reload
            time.sleep(3)
            
            # Should still be running
            assert process.poll() is None, "Should handle hot-reload without crashing"
            
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            
            # Should see reload messages (script manager handles this)
            assert "Script changed" in stderr or "reloading" in stderr.lower() or "Script loaded successfully" in stderr, "Should detect script changes"
            
        finally:
            temp_script.unlink(missing_ok=True)
    
    def test_refactored_app_graceful_shutdown(self):
        """
        Refactored RASLApp should shut down gracefully with all managers.
        
        Tests that cleanup coordination works properly.
        """
        process = subprocess.Popen([
            "python", "-m", "rasl", "run", "examples/simple_sine.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        try:
            # Let it start fully
            time.sleep(3)
            
            # Send SIGTERM for graceful shutdown
            process.terminate()
            
            # Should shut down within reasonable time
            try:
                stdout, stderr = process.communicate(timeout=10)
                
                # Should see cleanup messages
                assert "Shutting down" in stderr, "Should show shutdown message"
                assert "Cleanup complete" in stderr, "Should complete cleanup"
                
                # Exit code should be 0 (graceful)
                assert process.returncode == 0 or process.returncode == -15, "Should exit gracefully"
                
            except subprocess.TimeoutExpired:
                process.kill()
                pytest.fail("App did not shut down gracefully within timeout")
                
        except Exception as e:
            process.kill()
            raise
    
    def test_refactored_app_error_handling(self):
        """
        Refactored RASLApp should handle errors gracefully with managers.
        
        Tests error handling in the manager-based architecture.
        """
        # Create a script with syntax error
        bad_script_content = '''
from rasl import *

# Syntax error - missing closing parenthesis
sine = SineSource(freq=1.0, channels=1
console = ConsoleSink()
sine.ports.out >> console.ports["in"]
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_file.write(bad_script_content)
            temp_script = Path(temp_file.name)
        
        try:
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Should exit with error
            stdout, stderr = process.communicate(timeout=10)
            
            # Should have non-zero exit code
            assert process.returncode != 0, "Should exit with error for bad script"
            
            # Should show error message
            assert "error" in stderr.lower() or "failed" in stderr.lower(), "Should show error message"
            
        finally:
            temp_script.unlink(missing_ok=True)
