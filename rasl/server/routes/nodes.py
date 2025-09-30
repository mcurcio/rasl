"""
Node management API routes.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/nodes", tags=["nodes"])

@router.get("/")
async def list_nodes():
    """List all nodes in the current graph."""
    # TODO: Implement node listing
    return {"nodes": []}

@router.get("/{node_id}")
async def get_node(node_id: str):
    """Get details for a specific node."""
    # TODO: Implement node details
    return {"node_id": node_id, "status": "not_implemented"}

@router.post("/{node_id}/parameters")
async def update_node_parameters(node_id: str, parameters: dict):
    """Update parameters for a specific node."""
    # TODO: Implement parameter updates
    return {"node_id": node_id, "updated": parameters}
