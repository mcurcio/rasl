"""
Script loading and graph extraction for RASL.

Safely loads user Python scripts and extracts the graph definition
for execution by the RASL engine.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from rasl.core.nodes import Node, Sink
from rasl.core.ports import reset_connections
from .api import clear_exposed_parameters
from .syntax_validator import SyntaxValidator, ScriptLoadError
from .executor import ScriptExecutor
from .graph_extractor import GraphExtractor
from .parameter_discoverer import ParameterDiscoverer
from .graph_validator import GraphValidator

logger = logging.getLogger(__name__)


@dataclass
class GraphSpec:
    """Specification of a loaded graph."""
    nodes: List[Node]
    sinks: List[Sink]
    exposed_parameters: List[Dict[str, Any]]
    script_path: Path
    script_hash: str


class ScriptLoader:
    """
    Loads and validates user RASL scripts.
    
    Provides safe execution environment and extracts graph definitions
    for use by the RASL engine.
    """
    
    def __init__(self):
        self._last_hash: Optional[str] = None
        
        # Composed services for different responsibilities
        self._syntax_validator = SyntaxValidator()
        self._executor = ScriptExecutor()
        self._graph_extractor = GraphExtractor()
        self._parameter_discoverer = ParameterDiscoverer()
        self._graph_validator = GraphValidator()
    
    async def load_script(self, script_path: Path) -> GraphSpec:
        """
        Load a RASL script and extract the graph definition.
        
        Args:
            script_path: Path to the Python script file
            
        Returns:
            GraphSpec containing nodes, sinks, and metadata
            
        Raises:
            ScriptLoadError: If script loading or validation fails
        """
        if not script_path.exists():
            raise ScriptLoadError(f"Script file not found: {script_path}")
        
        if not script_path.suffix == ".py":
            raise ScriptLoadError(f"Script must be a Python file: {script_path}")
        
        logger.info(f"Loading script: {script_path}")
        
        try:
            # Calculate script hash for change detection
            script_content = script_path.read_text()
            script_hash = str(hash(script_content))
            
            # Reset global state
            reset_connections()
            clear_exposed_parameters()
            
            # Validate script syntax
            self._syntax_validator.validate_syntax(script_content, script_path)
            
            # Execute script in controlled environment
            script_globals = self._executor.create_script_environment()
            self._executor.execute_script(script_content, script_path, script_globals)
            
            # Extract graph from execution results
            nodes, sinks = self._graph_extractor.extract_graph(script_globals)
            
            # Auto-discover parameters from all nodes
            exposed_params = self._parameter_discoverer.discover_parameters(nodes)
            
            # Validate the extracted graph
            self._graph_validator.validate_graph(nodes, sinks)
            
            self._last_hash = script_hash
            
            return GraphSpec(
                nodes=nodes,
                sinks=sinks,
                exposed_parameters=exposed_params,
                script_path=script_path,
                script_hash=script_hash
            )
            
        except Exception as e:
            logger.error(f"Failed to load script {script_path}: {e}")
            raise ScriptLoadError(f"Script loading failed: {e}") from e
    
    def has_script_changed(self, script_path: Path) -> bool:
        """Check if script has changed since last load."""
        if not script_path.exists():
            return True
        
        try:
            current_content = script_path.read_text()
            current_hash = str(hash(current_content))
            return current_hash != self._last_hash
        except Exception:
            return True
    
    @property
    def discovered_nodes(self) -> Dict[str, Node]:
        """Get all discovered nodes from the last successful load."""
        return self._graph_extractor.discovered_nodes


class ScriptValidator:
    """
    Static analysis and validation of RASL scripts.
    
    Provides additional safety checks and analysis without execution.
    """
    
    def __init__(self):
        self._syntax_validator = SyntaxValidator()
    
    def validate_script_safety(self, script_path: Path) -> List[str]:
        """
        Perform static safety analysis of a script.
        
        Returns list of warnings/issues found.
        """
        return self._syntax_validator.validate_safety(script_path)
    
    def extract_script_metadata(self, script_path: Path) -> Dict[str, Any]:
        """Extract metadata from script without execution."""
        metadata = {
            "path": str(script_path),
            "size_bytes": script_path.stat().st_size,
            "modified_time": script_path.stat().st_mtime,
            "imports": [],
            "node_types": [],
            "estimated_complexity": "unknown"
        }
        
        try:
            content = script_path.read_text()
            tree = ast.parse(content)
            
            # Extract imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        metadata["imports"].append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        metadata["imports"].append(node.module)
            
            # Estimate complexity based on AST size
            node_count = len(list(ast.walk(tree)))
            if node_count < 50:
                metadata["estimated_complexity"] = "simple"
            elif node_count < 200:
                metadata["estimated_complexity"] = "moderate"
            else:
                metadata["estimated_complexity"] = "complex"
        
        except Exception as e:
            metadata["parse_error"] = str(e)
        
        return metadata
