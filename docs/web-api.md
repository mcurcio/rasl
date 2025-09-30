# Web API and UI Integration

RASL provides comprehensive REST and WebSocket APIs for monitoring, controlling, and integrating with the execution engine. This document details the web interface architecture and API specifications.

## Architecture Overview

### FastAPI Application Structure
```python
# rasl/server/app.py
def create_web_app(
    engine_provider: Callable[[], Optional[Engine]],
    monitor: NodeMonitor,
    config: Config
) -> FastAPI:
    """Create the main RASL web application."""
```

**Key Components**:
- **REST API**: Synchronous operations (graph inspection, parameter updates)
- **WebSocket Streams**: Real-time data (metrics, events, sample previews)
- **Static UI**: Embedded monitoring interface (served from `rasl/ui/dist/`)
- **CORS Support**: Cross-origin requests for development
- **Authentication**: Optional API key protection (future)

### Route Organization
```
/api/v1/
├── graph/          # Graph structure and manipulation
├── nodes/          # Individual node control
├── monitoring/     # Metrics and health data
└── ws/            # WebSocket endpoints
```

## REST API Specification

### Graph Operations

#### Get Graph Structure
```http
GET /api/v1/graph
```

**Response**:
```json
{
  "nodes": [
    {
      "id": "sine_1",
      "type": "SineSource", 
      "liveness": "generator",
      "params": {
        "freq": 1.0,
        "amplitude": 0.8,
        "channels": 150
      },
      "ports": {
        "out": {
          "kind": "output",
          "schema": {
            "components": [
              {
                "name": "Scalar",
                "channels": [
                  {"name": "ch0", "unit": "unitless", "range": {"min": -10.0, "max": 10.0}}
                ]
              }
            ]
          }
        }
      }
    }
  ],
  "edges": [
    ["sine_1", "out", "amp_1", "in"],
    ["amp_1", "out", "sacn_1", "in"]
  ],
  "execution_mode": "controllable",
  "duration": null,
  "adapters": []
}
```

#### Update Graph (Hot Reload)
```http
POST /api/v1/graph
Content-Type: application/json

{
  "script_content": "from rasl import *\n\nsine = SineSource(freq=2.0)...",
  "validate_only": false
}
```

**Response**:
```json
{
  "success": true,
  "validation_errors": [],
  "graph_id": "abc123",
  "nodes_added": ["sine_2"],
  "nodes_removed": ["sine_1"],
  "nodes_modified": ["amp_1"]
}
```

### Node Operations

#### Get Node Details
```http
GET /api/v1/nodes/{node_id}
```

**Response**:
```json
{
  "id": "sine_1",
  "type": "SineSource",
  "status": "running",
  "params": {
    "freq": {"value": 1.0, "min": 0.1, "max": 10.0, "type": "float"},
    "amplitude": {"value": 0.8, "min": 0.0, "max": 2.0, "type": "float"}
  },
  "ports": {
    "out": {
      "schema": {...},
      "connections": [{"dst_node": "amp_1", "dst_port": "in"}]
    }
  },
  "metrics": {
    "success_rate": 1.0,
    "avg_execution_time_ms": 0.15,
    "last_error": null
  }
}
```

#### Update Node Parameters
```http
PATCH /api/v1/nodes/{node_id}
Content-Type: application/json

{
  "params": {
    "freq": 2.5,
    "amplitude": 1.2
  }
}
```

**Response**:
```json
{
  "success": true,
  "updated_params": ["freq", "amplitude"],
  "validation_errors": []
}
```

### Monitoring Operations

#### Get System Metrics
```http
GET /api/v1/monitoring/metrics?since=1234567890&categories=performance,health
```

**Response**:
```json
{
  "timestamp": 1234567890.123,
  "engine": {
    "execution_mode": "controllable",
    "frame_rate": 59.8,
    "frame_budget_utilization": 0.65,
    "consecutive_errors": 0
  },
  "nodes": {
    "sine_1": {
      "success_rate": 1.0,
      "avg_execution_time_ms": 0.15,
      "memory_usage_mb": 2.1
    }
  },
  "system": {
    "cpu_usage": 0.25,
    "memory_usage_mb": 156.7,
    "uptime_seconds": 3600
  }
}
```

#### Get Health Status
```http
GET /api/v1/monitoring/health
```

**Response**:
```json
{
  "status": "healthy",
  "engine_running": true,
  "nodes_healthy": 5,
  "nodes_failed": 0,
  "alerts": [],
  "last_frame_time": 1234567890.123
}
```

## WebSocket API

### Connection
```javascript
const ws = new WebSocket('ws://localhost:8080/api/v1/ws/stream');
```

### Subscription Topics
```json
{
  "action": "subscribe",
  "topics": ["metrics", "events", "samples"],
  "filters": {
    "node_ids": ["sine_1", "amp_1"],
    "event_types": ["parameter_change", "node_error"]
  }
}
```

### Message Types

#### Metrics Stream
```json
{
  "type": "metrics",
  "timestamp": 1234567890.123,
  "data": {
    "frame_rate": 59.8,
    "nodes": {
      "sine_1": {"execution_time_ms": 0.12}
    }
  }
}
```

#### Event Stream
```json
{
  "type": "event",
  "timestamp": 1234567890.123,
  "event": "parameter_change",
  "data": {
    "node_id": "sine_1",
    "param": "freq",
    "old_value": 1.0,
    "new_value": 2.5
  }
}
```

#### Sample Preview Stream
```json
{
  "type": "samples",
  "timestamp": 1234567890.123,
  "data": {
    "sine_1.out": [0.5, 0.8, 0.3, -0.2],
    "amp_1.out": [0.4, 0.64, 0.24, -0.16]
  }
}
```

## UI Architecture

### Embedded Web Interface
The RASL web UI is served from `rasl/ui/dist/` and provides:

**Core Views**:
- **Graph Visualization**: Real-time node graph with data flow
- **Parameter Control**: Live parameter adjustment with validation
- **Performance Monitoring**: Frame rates, execution times, system health
- **Event Log**: System events, errors, and state changes

**Future Views**:
- **Timeline View**: For deterministic graphs with scrubbing
- **Export Control**: Offline rendering configuration
- **Plugin Management**: Install/configure plugin nodes

### UI Technology Stack (Planned)
- **Frontend**: React + TypeScript
- **Build System**: Vite for fast development and optimized builds
- **Visualization**: D3.js for graph rendering, Chart.js for metrics
- **State Management**: React Query for API state, Zustand for UI state
- **WebSocket**: Native WebSocket with reconnection logic

### Graph Visualization Features

#### Node Graph Display
```typescript
interface NodeGraphProps {
  nodes: Node[];
  edges: Edge[];
  selectedNode?: string;
  onNodeSelect: (nodeId: string) => void;
  onParameterChange: (nodeId: string, param: string, value: any) => void;
}
```

**Features**:
- **Interactive Layout**: Drag nodes, zoom/pan canvas
- **Real-time Data Flow**: Animated data flow visualization
- **Port Inspection**: Hover for schema details
- **Connection Validation**: Visual feedback for invalid connections
- **Performance Overlay**: Color-code nodes by execution time

#### Parameter Control Panel
```typescript
interface ParameterControlProps {
  nodeId: string;
  parameters: ParameterSpec[];
  values: Record<string, any>;
  onChange: (param: string, value: any) => void;
}
```

**Control Types**:
- **Sliders**: Numeric parameters with min/max bounds
- **Dropdowns**: Enumerated choices
- **Color Pickers**: Color parameters with preview
- **Text Inputs**: String parameters with validation
- **Toggle Switches**: Boolean parameters

### Real-time Updates

#### WebSocket Integration
```typescript
class RASLWebSocket {
  private ws: WebSocket;
  private subscriptions: Map<string, (data: any) => void>;
  
  subscribe(topic: string, callback: (data: any) => void): void {
    this.subscriptions.set(topic, callback);
    this.send({
      action: 'subscribe',
      topics: [topic]
    });
  }
  
  updateParameter(nodeId: string, param: string, value: any): void {
    fetch(`/api/v1/nodes/${nodeId}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({params: {[param]: value}})
    });
  }
}
```

#### State Synchronization
```typescript
// React Query for REST API state
const { data: graph } = useQuery(['graph'], fetchGraph, {
  refetchInterval: 5000  // Fallback polling
});

// WebSocket for real-time updates
useWebSocket('ws://localhost:8080/api/v1/ws/stream', {
  onMessage: (event) => {
    const message = JSON.parse(event.data);
    if (message.type === 'metrics') {
      updateMetrics(message.data);
    }
  }
});
```

## Development and Deployment

### Development Mode
```python
# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Production Deployment
```python
# Serve static UI files
if ui_dist_path.exists():
    app.mount("/", StaticFiles(directory=str(ui_dist_path), html=True))
else:
    # Fallback API-only mode
    @app.get("/")
    async def root():
        return {"message": "RASL API Server", "docs": "/api/docs"}
```

### Security Considerations

#### API Authentication (Future)
```python
@app.middleware("http")
async def authenticate_request(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        api_key = request.headers.get("X-API-Key")
        if not validate_api_key(api_key):
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid API key"}
            )
    return await call_next(request)
```

#### Rate Limiting
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/v1/nodes/{node_id}")
@limiter.limit("10/minute")  # Prevent parameter spam
async def update_node_parameters(request: Request, node_id: str):
    # Parameter update logic
```

## Integration Examples

### Python Client
```python
import requests
import websocket

class RASLClient:
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        
    def get_graph(self) -> dict:
        response = requests.get(f"{self.base_url}/api/v1/graph")
        return response.json()
        
    def update_parameter(self, node_id: str, param: str, value: any):
        response = requests.patch(
            f"{self.base_url}/api/v1/nodes/{node_id}",
            json={"params": {param: value}}
        )
        return response.json()
```

### JavaScript Integration
```javascript
class RASLController {
  constructor(baseUrl = 'http://localhost:8080') {
    this.baseUrl = baseUrl;
    this.ws = new WebSocket(`ws://localhost:8080/api/v1/ws/stream`);
  }
  
  async updateParameter(nodeId, param, value) {
    const response = await fetch(`${this.baseUrl}/api/v1/nodes/${nodeId}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({params: {[param]: value}})
    });
    return response.json();
  }
}
```

This web API architecture provides comprehensive access to RASL's capabilities while maintaining real-time performance and enabling rich UI experiences.
