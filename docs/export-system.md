# Export System Architecture

RASL's export system enables offline rendering of deterministic and controllable graphs to various file formats. This bridges RASL's real-time execution model with traditional sequence-based lighting tools like xLights.

## Export Capabilities by Execution Mode

### DETERMINISTIC Mode
**Condition**: Only FINITE sources present
**Export Features**:
- **Predictable Duration**: Calculate exact sequence length from finite sources
- **Full Offline Rendering**: No real-time constraints, can render faster than real-time
- **Format Support**: fseq, CSV, JSON, video (future)
- **Quality Options**: High-precision rendering without frame budget limits

### CONTROLLABLE Mode  
**Condition**: FINITE + GENERATOR sources (no STREAMING)
**Export Features**:
- **User-Specified Duration**: Export for exact time period or until finite sources complete
- **Generator Control**: GENERATOR sources run until duration limit or natural completion
- **Duration Policies**: Multiple strategies for determining export length
- **Partial Rendering**: Export specific time ranges

### LIVE Mode
**Condition**: Any STREAMING sources present
**Export Limitations**:
- **No Offline Export**: Streaming sources cannot be predicted or controlled
- **Real-time Recording Only**: Can record live output but not pre-render
- **Format Restrictions**: Limited to real-time compatible formats

## Duration Determination

### Duration Policies
```python
@dataclass
class ExportPolicy:
    duration_mode: Literal["shortest_finite", "longest_finite", "user_specified"]
    duration_seconds: Optional[float] = None
    loop_finite_sources: bool = False
    
class ExportEngine:
    def calculate_duration(self, graph: Graph, policy: ExportPolicy) -> float:
        """Calculate export duration based on policy."""
```

**Policy Behaviors**:

#### shortest_finite
Export ends when the first FINITE source completes:
```python
# CSV file: 10 seconds, Audio file: 30 seconds
# Export duration: 10 seconds (CSV completes first)
csv = CSVSource("short_data.csv")      # 10s duration
audio = AudioSource("long_song.mp3")   # 30s duration
mixer = AudioMix()

csv >> mixer.ports.a
audio >> mixer.ports.b  # Will be truncated at 10s
```

#### longest_finite  
Export continues until the last FINITE source completes:
```python
# Export duration: 30 seconds (audio completes last)
# CSV will loop or hold_last to fill the duration
csv = CSVSource("short_data.csv")      # 10s duration, will loop
audio = AudioSource("long_song.mp3")   # 30s duration
```

#### user_specified
Export for exactly the specified duration:
```python
# Export duration: 60 seconds (user specified)
# All sources adapt to this duration
policy = ExportPolicy(
    duration_mode="user_specified",
    duration_seconds=60.0
)
```

### Duration Calculation Algorithm
```python
def calculate_graph_duration(graph: Graph, policy: ExportPolicy) -> float:
    finite_sources = [n for n in graph.sources if n.base_liveness == Liveness.FINITE]
    
    if policy.duration_mode == "user_specified":
        return policy.duration_seconds
    
    source_durations = []
    for source in finite_sources:
        duration = source.calculate_duration()
        if source.loop_count > 1:
            duration *= source.loop_count
        source_durations.append(duration)
    
    if policy.duration_mode == "shortest_finite":
        return min(source_durations)
    elif policy.duration_mode == "longest_finite":
        return max(source_durations)
```

## Export Formats

### xLights FSEQ Format
**Purpose**: Interoperability with xLights sequencer
**Features**:
- **Frame-based storage**: Fixed frame rate with channel data per frame
- **Compression**: Optional compression for large sequences
- **Metadata**: Timing information, channel mapping, model definitions

```python
class FSEQExporter:
    def __init__(self, filename: str, fps: int = 30, channels: int = 512):
        self.filename = filename
        self.fps = fps
        self.channels = channels
        
    def export_graph(self, graph: Graph, duration: float) -> None:
        """Export graph to FSEQ format."""
        total_frames = int(duration * self.fps)
        
        with FSEQWriter(self.filename, self.fps, self.channels) as writer:
            for frame_idx in range(total_frames):
                frame_time = frame_idx / self.fps
                frame = Frame(t=frame_time, dt=1.0/self.fps, seq=frame_idx)
                
                # Render frame offline
                frame_data = self._render_frame(graph, frame)
                writer.write_frame(frame_data)
```

### CSV Export
**Purpose**: Data analysis, debugging, custom processing
**Features**:
- **Human-readable**: Text format for inspection and analysis
- **Flexible schema**: Configurable column layout and precision
- **Metadata headers**: Graph structure, timing information

```python
class CSVExporter:
    def export_graph(self, graph: Graph, duration: float, fps: float = 60.0) -> None:
        """Export graph data to CSV format."""
        with open(self.filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write metadata header
            writer.writerow(['# RASL Export'])
            writer.writerow(['# Duration:', duration])
            writer.writerow(['# FPS:', fps])
            writer.writerow(['# Nodes:', len(graph.nodes)])
            writer.writerow([])
            
            # Write column headers
            headers = ['time', 'frame']
            for node in graph.sinks:
                for port_name in node.output_ports:
                    headers.extend([f"{node.id}.{port_name}.ch{i}" 
                                  for i in range(node.get_channel_count(port_name))])
            writer.writerow(headers)
            
            # Write frame data
            total_frames = int(duration * fps)
            for frame_idx in range(total_frames):
                frame_time = frame_idx / fps
                frame = Frame(t=frame_time, dt=1.0/fps, seq=frame_idx)
                
                row = [frame_time, frame_idx]
                frame_data = self._render_frame(graph, frame)
                for node_data in frame_data.values():
                    row.extend(node_data)
                writer.writerow(row)
```

### JSON Export
**Purpose**: Structured data, web applications, API integration
**Features**:
- **Structured format**: Hierarchical data with metadata
- **Schema validation**: JSON schema for format verification
- **Extensible**: Easy to add custom metadata and annotations

```python
class JSONExporter:
    def export_graph(self, graph: Graph, duration: float, fps: float = 60.0) -> None:
        """Export graph to structured JSON format."""
        export_data = {
            "metadata": {
                "format_version": "1.0",
                "exported_at": datetime.utcnow().isoformat(),
                "duration_seconds": duration,
                "fps": fps,
                "total_frames": int(duration * fps)
            },
            "graph": {
                "nodes": [node.to_dict() for node in graph.nodes],
                "edges": [[e.src_id, e.src_port, e.dst_id, e.dst_port] 
                         for e in graph.edges]
            },
            "frames": []
        }
        
        # Render and store frame data
        total_frames = int(duration * fps)
        for frame_idx in range(total_frames):
            frame_time = frame_idx / fps
            frame = Frame(t=frame_time, dt=1.0/fps, seq=frame_idx)
            
            frame_data = self._render_frame(graph, frame)
            export_data["frames"].append({
                "time": frame_time,
                "sequence": frame_idx,
                "data": frame_data
            })
        
        with open(self.filename, 'w') as f:
            json.dump(export_data, f, indent=2)
```

## Offline Rendering Engine

### Rendering Architecture
```python
class OfflineRenderer:
    def __init__(self, graph: Graph):
        self.graph = graph
        self.executor = Executor()
        self.validator = Validator()
        
        # Register all nodes with executor
        for node in graph.nodes:
            self.executor.register_node(node)
    
    def render_sequence(self, duration: float, fps: float = 60.0) -> Iterator[Dict[str, NDArrayLike]]:
        """Render graph offline at specified frame rate."""
        total_frames = int(duration * fps)
        
        for frame_idx in range(total_frames):
            frame_time = frame_idx / fps
            frame = Frame(t=frame_time, dt=1.0/fps, seq=frame_idx)
            
            # Reset executor cache for new frame
            self.executor.reset_frame_cache(frame)
            
            # Materialize all sink inputs
            frame_data = {}
            for sink in self.graph.sinks:
                try:
                    inputs = {}
                    for port_ref in sink.input_ports:
                        data = await self.executor.materialize(port_ref, frame)
                        inputs[port_ref.name] = data
                    frame_data[sink.id] = inputs
                except Exception as e:
                    logger.error(f"Failed to render {sink.id} at frame {frame_idx}: {e}")
                    frame_data[sink.id] = None
            
            yield frame_data
```

### Performance Optimizations

#### Parallel Rendering
```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

class ParallelOfflineRenderer:
    def __init__(self, graph: Graph, worker_count: int = None):
        self.graph = graph
        self.worker_count = worker_count or os.cpu_count()
    
    async def render_sequence_parallel(self, duration: float, fps: float = 60.0) -> List[Dict[str, NDArrayLike]]:
        """Render sequence using multiple processes."""
        total_frames = int(duration * fps)
        chunk_size = max(1, total_frames // self.worker_count)
        
        tasks = []
        for i in range(0, total_frames, chunk_size):
            end_frame = min(i + chunk_size, total_frames)
            task = self._render_chunk(i, end_frame, fps)
            tasks.append(task)
        
        chunks = await asyncio.gather(*tasks)
        
        # Combine chunks in order
        result = []
        for chunk in chunks:
            result.extend(chunk)
        return result
```

#### Memory Management
```python
class StreamingRenderer:
    def render_to_file(self, exporter: Exporter, duration: float, fps: float = 60.0) -> None:
        """Stream rendering directly to file to minimize memory usage."""
        exporter.begin_export(duration, fps)
        
        try:
            for frame_data in self.render_sequence(duration, fps):
                exporter.write_frame(frame_data)
                
                # Explicit cleanup for large sequences
                if frame_data:
                    del frame_data
                    
        finally:
            exporter.end_export()
```

## Export API

### Command Line Interface
```bash
# Export deterministic graph
rasl export my_show.py --format fseq --output show.fseq --fps 30

# Export with specific duration
rasl export my_show.py --format csv --duration 60 --output data.csv

# Export time range
rasl export my_show.py --format json --start 10 --end 30 --output segment.json
```

### Python API
```python
from rasl.export import ExportEngine, FSEQExporter, ExportPolicy

# Load graph from script
graph = load_graph_from_script("my_show.py")

# Configure export
policy = ExportPolicy(
    duration_mode="longest_finite",
    loop_finite_sources=True
)

exporter = FSEQExporter("output.fseq", fps=30, channels=512)
export_engine = ExportEngine(graph, policy)

# Perform export
await export_engine.export(exporter)
```

### Web API Integration
```http
POST /api/v1/export
Content-Type: application/json

{
  "format": "fseq",
  "duration_policy": "user_specified",
  "duration_seconds": 120.0,
  "fps": 30,
  "output_filename": "my_sequence.fseq"
}
```

## xLights Integration

### FSEQ Import Workflow
1. **Create RASL Script**: Define graph with desired effects
2. **Export to FSEQ**: Use offline renderer to generate sequence file
3. **Import to xLights**: Load FSEQ as sequence in xLights
4. **Model Mapping**: Map FSEQ channels to xLights models
5. **Playback**: Use xLights scheduler for hardware output

### Bidirectional Workflow
```python
# RASL → xLights
rasl_graph = create_lighting_graph()
export_to_fseq(rasl_graph, "rasl_sequence.fseq")

# xLights → RASL (future feature)
fseq_source = FSEQSource("xlights_sequence.fseq")
live_overlay = NetworkSource("live_controls")
mixer = SequenceMix()

fseq_source >> mixer.ports.base
live_overlay >> mixer.ports.overlay
mixer >> SACNSink(universe=1)
```

### Model Definition Bridge
Future integration could support xLights model definitions:
```python
# Import xLights model configuration
xlights_models = import_xlights_models("show_setup.xml")

# Create RASL sinks from model definitions
sinks = []
for model in xlights_models:
    sink = SACNSink(
        universe=model.universe,
        start_channel=model.start_channel,
        channel_count=model.channel_count
    )
    sinks.append(sink)
```

This export system enables RASL to serve as both a real-time animation engine and a sequence generation tool, bridging the gap between programmatic control and traditional lighting workflows.
