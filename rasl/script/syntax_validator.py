"""
Script syntax validation for RASL.

Handles Python syntax validation and static analysis of user scripts
before execution.
"""

import ast
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class ScriptLoadError(Exception):
    """Raised when script loading fails."""
    pass


class SyntaxValidator:
    """
    Validates Python syntax and performs static analysis of RASL scripts.
    
    Provides safety checks and syntax validation without execution.
    """
    
    def __init__(self):
        pass
    
    def validate_syntax(self, content: str, script_path: Path) -> None:
        """
        Validate Python syntax without executing.
        
        Args:
            content: Script content to validate
            script_path: Path to script file (for error reporting)
            
        Raises:
            ScriptLoadError: If syntax validation fails
        """
        try:
            ast.parse(content, filename=str(script_path))
        except SyntaxError as e:
            raise ScriptLoadError(f"Syntax error in {script_path}:{e.lineno}: {e.msg}")
    
    def validate_safety(self, script_path: Path) -> List[str]:
        """
        Perform static safety analysis of a script.
        
        Args:
            script_path: Path to script file to analyze
            
        Returns:
            List of warnings/issues found
        """
        warnings = []
        
        try:
            content = script_path.read_text()
            tree = ast.parse(content)
            
            # Check for potentially dangerous operations
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in ('os', 'subprocess', 'sys'):
                            warnings.append(f"Potentially unsafe import: {alias.name}")
                
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ('exec', 'eval', 'open'):
                            warnings.append(f"Potentially unsafe function call: {node.func.id}")
        
        except Exception as e:
            warnings.append(f"Failed to analyze script: {e}")
        
        return warnings
