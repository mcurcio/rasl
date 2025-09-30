"""
Graph inspection and control API routes.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from rasl.core.engine import Engine
from rasl.core.monitor import NodeMonitor
from rasl.core.ports import get_connection_registry

logger = logging.getLogger(__name__)

router = APIRouter()


class GraphInfo(BaseModel):
    """Graph information response model."""
    node_count: int
    edge_count: int
    sink_count: int
    running: bool
    health: str


class NodeInfo(BaseModel):
    """Node information model."""
    id: str
    type: str
    kind: str  # source, transform, sink
    params: Dict[str, Any]
    ports: Dict[str, Dict[str, Any]]
    state: str
    performance: Optional[Dict[str, Any]] = None


class EdgeInfo(BaseModel):
    """Edge information model."""
    src_id: str
    src_port: str
    dst_id: str
    dst_port: str


class GraphSpec(BaseModel):
    """Complete graph specification."""
    nodes: List[NodeInfo]
    edges: List[EdgeInfo]
    metadata: Dict[str, Any]


def get_engine(request) -> Optional[Engine]:
    """Dependency to get current engine instance."""
    return request.app.state.engine_provider()


def get_monitor(request) -> NodeMonitor:
    """Dependency to get node monitor."""
    return request.app.state.monitor


@router.get("/info", response_model=GraphInfo)
async def get_graph_info(
    engine: Optional[Engine] = Depends(get_engine),
    monitor: NodeMonitor = Depends(get_monitor)
):
    """Get basic graph information."""
    
    if not engine:
        return GraphInfo(
            node_count=0,
            edge_count=0,
            sink_count=0,
            running=False,
            health="no_engine"
        )
    
    # Get connection registry info
    registry = get_connection_registry()
    edges = registry.get_edges()
    
    # Get health summary
    health_summary = monitor.get_health_summary()
    
    return GraphInfo(
        node_count=health_summary.get("total_nodes", 0),
        edge_count=len(edges),
        sink_count=len(engine.sinks),
        running=engine._running,
        health=health_summary.get("overall_health", "unknown")
    )


@router.get("/spec", response_model=GraphSpec)
async def get_graph_spec(
    engine: Optional[Engine] = Depends(get_engine),
    monitor: NodeMonitor = Depends(get_monitor)
):
    """Get complete graph specification."""
    
    if not engine:
        raise HTTPException(status_code=404, detail="No engine available")
    
    # Collect node information
    nodes = []
    node_statuses = monitor.get_all_node_statuses()
    
    # Get nodes from sinks (this is a limitation - we need better node tracking)
    all_nodes = []
    
    # Discover nodes from connection registry
    registry = get_connection_registry()
    edges = registry.get_edges()
    
    # For now, we can only provide information about sinks
    # TODO: Implement proper node registry in engine
    for sink in engine.sinks:
        status = node_statuses.get(sink.id)
        
        node_info = NodeInfo(
            id=sink.id,
            type=sink.TYPE,
            kind=sink.KIND,
            params=sink.get_params(),
            ports={
                port.name: {
                    "kind": port.kind,
                    "schema": {
                        "components": [
                            {
                                "name": comp.name,
                                "flavor": comp.flavor,
                                "channels": [
                                    {
                                        "id": ch.id,
                                        "units": ch.units,
                                        "range": {
                                            "min": ch.range.min,
                                            "max": ch.range.max,
                                            "rule": ch.range.rule.value
                                        }
                                    }
                                    for ch in comp.channels
                                ]
                            }
                            for comp in port.schema.components
                        ]
                    }
                }
                for port in sink.ports.list()
            },
            state=status.state.value if status else "unknown",
            performance={
                "avg_eval_time_ms": status.avg_eval_time * 1000 if status else 0,
                "total_evaluations": status.total_evaluations if status else 0,
                "error_count": status.error_count if status else 0
            } if status else None
        )
        
        nodes.append(node_info)
    
    # Convert edges
    edge_infos = [
        EdgeInfo(
            src_id=edge.src_id,
            src_port=edge.src_port,
            dst_id=edge.dst_id,
            dst_port=edge.dst_port
        )
        for edge in edges
    ]
    
    # Get performance summary
    perf_summary = monitor.get_performance_summary()
    
    return GraphSpec(
        nodes=nodes,
        edges=edge_infos,
        metadata={
            "engine_running": engine._running,
            "uptime_seconds": perf_summary.get("uptime_seconds", 0),
            "total_frames": perf_summary.get("total_frames", 0),
            "current_fps": perf_summary.get("current_fps", 0),
            "health": monitor.get_health_summary()
        }
    )


@router.post("/validate")
async def validate_graph(engine: Optional[Engine] = Depends(get_engine)):
    """Validate current graph structure."""
    
    if not engine:
        raise HTTPException(status_code=404, detail="No engine available")
    
    try:
        # Run validation
        engine.validator.validate_global(engine.sinks)
        
        return {
            "valid": True,
            "message": "Graph validation passed",
            "issues": []
        }
        
    except Exception as e:
        return {
            "valid": False,
            "message": f"Graph validation failed: {e}",
            "issues": [str(e)]
        }


@router.get("/topology")
async def get_graph_topology(engine: Optional[Engine] = Depends(get_engine)):
    """Get graph topology for visualization."""
    
    if not engine:
        raise HTTPException(status_code=404, detail="No engine available")
    
    registry = get_connection_registry()
    edges = registry.get_edges()
    
    # Build adjacency information
    nodes = set()
    adjacency = {}
    
    for edge in edges:
        nodes.add(edge.src_id)
        nodes.add(edge.dst_id)
        
        if edge.src_id not in adjacency:
            adjacency[edge.src_id] = {"outputs": [], "inputs": []}
        if edge.dst_id not in adjacency:
            adjacency[edge.dst_id] = {"outputs": [], "inputs": []}
        
        adjacency[edge.src_id]["outputs"].append({
            "target": edge.dst_id,
            "src_port": edge.src_port,
            "dst_port": edge.dst_port
        })
        
        adjacency[edge.dst_id]["inputs"].append({
            "source": edge.src_id,
            "src_port": edge.src_port,
            "dst_port": edge.dst_port
        })
    
    return {
        "nodes": list(nodes),
        "adjacency": adjacency,
        "edge_count": len(edges),
        "node_count": len(nodes)
    }
