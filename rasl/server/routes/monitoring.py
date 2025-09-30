"""
Monitoring and metrics API routes.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

@router.get("/status")
async def get_system_status():
    """Get overall system status."""
    # TODO: Implement system status
    return {"status": "running", "frame_rate": 0, "nodes": 0}

@router.get("/metrics")
async def get_metrics():
    """Get performance metrics."""
    # TODO: Implement metrics collection
    return {"metrics": {}}

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
