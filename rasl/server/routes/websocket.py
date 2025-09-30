"""
WebSocket routes for real-time communication.
"""

from fastapi import APIRouter, WebSocket

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket.accept()
    try:
        # TODO: Implement real-time updates
        await websocket.send_json({"type": "connected", "message": "WebSocket connected"})
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except Exception:
        pass
