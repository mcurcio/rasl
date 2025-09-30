"""
Integration tests for web interface functionality.

Tests that the web server starts correctly and responds to basic requests.
Verifies Milestone 1 requirement for web UI availability.
"""

import pytest
import subprocess
import time
import socket
from contextlib import closing


class TestWebInterface:
    """Test web interface functionality."""
    
    def test_web_server_starts_and_responds(self):
        """
        Test that web server starts and responds to requests.
        
        Verifies Milestone 1 requirement: "Web UI at http://localhost:8080 shows running graph"
        """
        # Start RASL
        process = subprocess.Popen([
            "python", "-m", "rasl", "run", "examples/simple_sine.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        try:
            # Wait for web server startup
            time.sleep(3)
            
            # Verify RASL process is running
            assert process.poll() is None, "RASL process should be running"
            
            # Test that port 8080 is open
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(5)
                result = sock.connect_ex(('localhost', 8080))
                assert result == 0, "Web server should be listening on port 8080"
            
            # Test health endpoint using curl
            result = subprocess.run([
                "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                "--connect-timeout", "5", "http://localhost:8080/api/health"
            ], capture_output=True, text=True)
            
            assert result.returncode == 0, "Health endpoint should be reachable"
            status_code = result.stdout.strip()
            assert status_code == "200", f"Health endpoint should return 200, got {status_code}"
            
        finally:
            # Cleanup
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
    
    def test_api_endpoints_respond(self):
        """
        Test that API endpoints are accessible.
        
        Even if not fully implemented, endpoints should respond
        (200 for implemented, 404 for not implemented).
        """
        process = subprocess.Popen([
            "python", "-m", "rasl", "run", "examples/simple_sine.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        try:
            time.sleep(3)
            assert process.poll() is None, "RASL process should be running"
            
            # Test various API endpoints
            endpoints = [
                ("/api/health", "200"),           # Should work
                ("/api/v1/graph", ["200", "404"]), # May not be implemented
                ("/api/v1/nodes", ["200", "404"]), # May not be implemented
                ("/api/docs", ["200", "404"]),     # FastAPI docs
            ]
            
            for endpoint, expected_codes in endpoints:
                if isinstance(expected_codes, str):
                    expected_codes = [expected_codes]
                
                result = subprocess.run([
                    "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                    "--connect-timeout", "5", f"http://localhost:8080{endpoint}"
                ], capture_output=True, text=True)
                
                assert result.returncode == 0, f"Should be able to connect to {endpoint}"
                status_code = result.stdout.strip()
                assert status_code in expected_codes, f"{endpoint} returned {status_code}, expected one of {expected_codes}"
                
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
    
    def test_web_server_shutdown_graceful(self):
        """
        Test that web server shuts down gracefully with RASL.
        
        Ensures no hanging processes or port conflicts.
        """
        process = subprocess.Popen([
            "python", "-m", "rasl", "run", "examples/simple_sine.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        try:
            time.sleep(2)
            assert process.poll() is None, "Process should be running"
            
            # Verify web server is up
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(2)
                assert sock.connect_ex(('localhost', 8080)) == 0, "Web server should be up"
            
            # Terminate gracefully
            process.terminate()
            process.wait(timeout=10)  # Give more time for graceful shutdown
            
            # Verify port is released
            time.sleep(1)  # Brief wait for port cleanup
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(2)
                result = sock.connect_ex(('localhost', 8080))
                assert result != 0, "Port 8080 should be released after shutdown"
                
        except subprocess.TimeoutExpired:
            process.kill()
            pytest.fail("Process did not shut down gracefully")
    
    def test_concurrent_web_requests(self):
        """
        Test that web server can handle multiple concurrent requests.
        
        Basic load test to ensure the server is stable.
        """
        process = subprocess.Popen([
            "python", "-m", "rasl", "run", "examples/simple_sine.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        try:
            time.sleep(3)
            assert process.poll() is None, "Process should be running"
            
            # Make multiple concurrent requests
            import concurrent.futures
            
            def make_request():
                result = subprocess.run([
                    "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                    "--connect-timeout", "5", "http://localhost:8080/api/health"
                ], capture_output=True, text=True)
                return result.returncode == 0 and result.stdout.strip() == "200"
            
            # Test 5 concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(make_request) for _ in range(5)]
                results = [future.result() for future in concurrent.futures.as_completed(futures)]
            
            # All requests should succeed
            assert all(results), "All concurrent requests should succeed"
            
            # Process should still be running
            assert process.poll() is None, "Process should survive concurrent requests"
            
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
