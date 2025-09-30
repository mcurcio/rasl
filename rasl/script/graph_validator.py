"""
Graph validation for RASL scripts.

Validates the structure and integrity of extracted graphs before
execution.
"""

import logging
from typing import List

from rasl.core.nodes import Node, Sink
from rasl.core.ports import get_connection_registry
from .syntax_validator import ScriptLoadError

logger = logging.getLogger(__name__)


class GraphValidator:
    """
    Validates RASL graph structure and integrity.
    
    Performs validation checks on extracted graphs to ensure they are
    valid for execution.
    """
    
    def __init__(self):
        pass
    
    def validate_graph(self, nodes: List[Node], sinks: List[Sink]) -> None:
        """
        Validate the extracted graph structure.
        
        Args:
            nodes: List of nodes in the graph
            sinks: List of sinks in the graph
            
        Raises:
            ScriptLoadError: If graph validation fails
        """
        # Basic validation
        if not nodes:
            raise ScriptLoadError("Graph contains no nodes")
        
        if not sinks:
            raise ScriptLoadError("Graph contains no sinks")
        
        # Check for duplicate node IDs
        node_ids = [node.id for node in nodes]
        if len(node_ids) != len(set(node_ids)):
            duplicates = [id for id in set(node_ids) if node_ids.count(id) > 1]
            raise ScriptLoadError(f"Duplicate node IDs found: {duplicates}")
        
        # Validate connections exist
        registry = get_connection_registry()
        edges = registry.get_edges()
        
        if not edges:
            logger.warning("No connections found in graph - nodes may be isolated")
        
        logger.info(f"Graph validation passed: {len(nodes)} nodes, {len(edges)} connections")
