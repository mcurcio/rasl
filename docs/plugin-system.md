# Plugin System Architecture

RASL's plugin system enables extending core functionality with custom nodes, file formats, and UI components while maintaining clean separation between core engine and domain-specific features.

## Design Principles

### Core vs Plugin Boundaries

**Core Responsibilities** (always available):
- Graph execution engine (scheduler, executor, validator, monitor)
- Base node classes and mixin architecture
- Port/connection system with schema validation
- Basic math operations (Float, Vector, Matrix)
- Web API framework and REST/WebSocket endpoints

**Plugin Territory** (optional extensions):
- Domain-specific nodes (audio, video, lighting effects)
- File format handlers (CSV, fseq, audio formats)
- Network protocols (sACN, Art-Net, OSC)
- Complex data types (Color spaces, 3D transforms)
- UI components and visualizations

### Plugin Architecture Goals

1. **Zero Core Dependencies**: Plugins don't affect core functionality
2. **Graceful Degradation**: Missing plugins don't break the system
3. **Hot Loading**: Plugins can be loaded/unloaded at runtime
4. **Namespace Isolation**: Plugins don't conflict with each other
5. **API Stability**: Plugin interfaces remain stable across versions

## Plugin Types

### Node Plugins
Extend the node library with custom sources, transforms, and sinks:

```python
# my_audio_plugin/nodes.py
from rasl.core.nodes import BaseSource, BaseTransform
from rasl.plugins import register_node

@register_node("audio")
class AudioSource(BaseSource):
    """Load and play audio files."""
    
    def __init__(self, file: str, **kwargs):
        self.file = file
        super().__init__(**kwargs)
    
    def _determine_base_liveness(self) -> Liveness:
        return Liveness.FINITE
    
    def _generate_data(self, frame: Frame) -> NDArrayLike:
        # Audio processing implementation
        pass

@register_node("audio") 
class FFTTransform(BaseTransform):
    """Compute frequency spectrum of audio."""
    
    def _transform_data(self, inputs: Dict[str, NDArrayLike], frame: Frame) -> Dict[str, NDArrayLike]:
        # FFT implementation
        pass
```

### Format Plugins
Add support for new file formats:

```python
# my_format_plugin/handlers.py
from rasl.plugins import register_format

@register_format("fseq")
class FSEQHandler:
    """xLights FSEQ format support."""
    
    @staticmethod
    def can_read(file_path: str) -> bool:
        return file_path.endswith('.fseq')
    
    @staticmethod
    def read(file_path: str) -> Iterator[NDArrayLike]:
        # FSEQ reading implementation
        pass
    
    @staticmethod
    def write(file_path: str, frames: Iterator[NDArrayLike]) -> None:
        # FSEQ writing implementation
        pass
```

### Protocol Plugins
Implement hardware communication protocols:

```python
# my_protocol_plugin/sinks.py
from rasl.core.nodes import BaseSink
from rasl.plugins import register_node

@register_node("lighting")
class SACNSink(BaseSink):
    """Output to sACN/E1.31 lighting controllers."""
    
    def __init__(self, universe: int, **kwargs):
        self.universe = universe
        super().__init__(**kwargs)
    
    def _emit_data(self, inputs: Dict[str, NDArrayLike], frame: Frame) -> None:
        # sACN protocol implementation
        pass
```

### UI Plugins
Extend the web interface with custom components:

```python
# my_ui_plugin/components.py
from rasl.plugins import register_ui_component

@register_ui_component("visualizer")
class SpectrumVisualizer:
    """Real-time audio spectrum display."""
    
    component_type = "react"
    
    @staticmethod
    def get_component_definition() -> dict:
        return {
            "name": "SpectrumVisualizer",
            "props": ["node_id", "fft_size"],
            "bundle_path": "/static/plugins/spectrum-visualizer.js"
        }
```

## Plugin Discovery and Registration

### Entry Points
Plugins register themselves via Python entry points:

```toml
# pyproject.toml for plugin package
[project.entry-points."rasl.plugins"]
audio_nodes = "my_audio_plugin.nodes"
fseq_format = "my_format_plugin.handlers"
sacn_protocol = "my_protocol_plugin.sinks"
spectrum_ui = "my_ui_plugin.components"
```

### Plugin Manager
Core system discovers and loads plugins automatically:

```python
# rasl/plugins/manager.py
class PluginManager:
    def __init__(self):
        self.loaded_plugins: Dict[str, Plugin] = {}
        self.node_registry: Dict[str, Type[Node]] = {}
        self.format_handlers: Dict[str, FormatHandler] = {}
        
    def discover_plugins(self) -> None:
        """Discover plugins via entry points."""
        import pkg_resources
        
        for entry_point in pkg_resources.iter_entry_points('rasl.plugins'):
            try:
                plugin_module = entry_point.load()
                self._register_plugin(entry_point.name, plugin_module)
            except Exception as e:
                logger.warning(f"Failed to load plugin {entry_point.name}: {e}")
    
    def _register_plugin(self, name: str, module) -> None:
        """Register a plugin module."""
        plugin = Plugin(name, module)
        
        # Register node types
        for node_class in getattr(module, 'NODE_TYPES', []):
            self.node_registry[node_class.TYPE] = node_class
            
        # Register format handlers
        for handler in getattr(module, 'FORMAT_HANDLERS', []):
            self.format_handlers[handler.format_name] = handler
            
        self.loaded_plugins[name] = plugin
```

### Runtime Registration
Plugins can also register components at runtime:

```python
# Plugin registration decorators
def register_node(category: str):
    def decorator(cls):
        PluginManager.instance().register_node_type(cls, category)
        return cls
    return decorator

def register_format(format_name: str):
    def decorator(cls):
        PluginManager.instance().register_format_handler(cls, format_name)
        return cls
    return decorator
```

## Plugin API Contracts

### Node Plugin Interface
```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Mapping

class PluginNode(ABC):
    """Base interface for plugin nodes."""
    
    TYPE: str  # Unique node type identifier
    CATEGORY: str  # Plugin category for organization
    
    @abstractmethod
    def param_spec(self) -> Mapping[str, Mapping[str, Any]]:
        """Parameter specifications for UI generation."""
        pass
    
    @abstractmethod
    def port_schema(self, name: str) -> Schema:
        """Port schema definitions."""
        pass
    
    @property
    @abstractmethod
    def dependencies(self) -> List[str]:
        """Required dependencies (for graceful degradation)."""
        pass
```

### Format Handler Interface
```python
class FormatHandler(ABC):
    """Base interface for file format handlers."""
    
    format_name: str
    file_extensions: List[str]
    
    @staticmethod
    @abstractmethod
    def can_read(file_path: str) -> bool:
        """Check if this handler can read the file."""
        pass
    
    @staticmethod
    @abstractmethod
    def can_write(file_path: str) -> bool:
        """Check if this handler can write the file."""
        pass
    
    @abstractmethod
    def read_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extract file metadata without full read."""
        pass
```

### UI Component Interface
```python
class UIComponent(ABC):
    """Base interface for UI plugin components."""
    
    component_type: Literal["react", "vue", "vanilla"]
    
    @abstractmethod
    def get_component_definition(self) -> Dict[str, Any]:
        """Component definition for UI framework."""
        pass
    
    @abstractmethod
    def get_static_assets(self) -> List[str]:
        """Static assets (JS, CSS) required by component."""
        pass
```

## Dependency Management

### Optional Dependencies
Plugins handle missing dependencies gracefully:

```python
class AudioSource(BaseSource):
    def __init__(self, **kwargs):
        try:
            import librosa
            self.librosa = librosa
        except ImportError:
            raise PluginDependencyError(
                "AudioSource requires 'librosa' package. "
                "Install with: pip install librosa"
            )
        super().__init__(**kwargs)
    
    @property
    def dependencies(self) -> List[str]:
        return ["librosa>=0.8.0"]
```

### Dependency Checking
Core system validates plugin dependencies:

```python
class PluginManager:
    def validate_plugin_dependencies(self, plugin: Plugin) -> ValidationResult:
        """Check if plugin dependencies are satisfied."""
        missing_deps = []
        
        for dep in plugin.dependencies:
            try:
                import importlib
                importlib.import_module(dep.split('>=')[0])
            except ImportError:
                missing_deps.append(dep)
        
        return ValidationResult(
            valid=len(missing_deps) == 0,
            missing_dependencies=missing_deps
        )
```

### Graceful Degradation
System continues operating with missing plugins:

```python
def create_node(node_type: str, **params) -> Optional[Node]:
    """Create node instance, return None if plugin unavailable."""
    try:
        node_class = PluginManager.instance().get_node_type(node_type)
        return node_class(**params)
    except PluginNotAvailableError:
        logger.warning(f"Node type '{node_type}' not available (missing plugin)")
        return None
```

## Plugin Development Guide

### Creating a Node Plugin

1. **Setup Plugin Package**:
```bash
mkdir my_rasl_plugin
cd my_rasl_plugin
touch pyproject.toml setup.py my_plugin/__init__.py
```

2. **Define Plugin Metadata**:
```toml
# pyproject.toml
[project]
name = "my-rasl-plugin"
version = "0.1.0"
dependencies = ["rasl>=0.1.0"]

[project.entry-points."rasl.plugins"]
my_nodes = "my_plugin.nodes"
```

3. **Implement Node Classes**:
```python
# my_plugin/nodes.py
from rasl.core.nodes import BaseSource
from rasl.plugins import register_node

@register_node("generators")
class RandomWalkSource(BaseSource):
    def __init__(self, step_size: float = 0.1, **kwargs):
        self.step_size = step_size
        self.current_value = 0.0
        super().__init__(**kwargs)
    
    def _determine_base_liveness(self) -> Liveness:
        return Liveness.GENERATOR
    
    def _generate_data(self, frame: Frame) -> NDArrayLike:
        import random
        self.current_value += random.uniform(-self.step_size, self.step_size)
        return [self.current_value]
```

4. **Test Plugin**:
```python
# test_plugin.py
def test_random_walk():
    walk = RandomWalkSource(step_size=0.5)
    frame = Frame(t=0.0, dt=0.1, seq=0)
    data = walk._generate_data(frame)
    assert len(data) == 1
    assert isinstance(data[0], float)
```

5. **Install and Use**:
```bash
pip install -e .
```

```python
# user_script.py
from rasl import *

# Plugin node now available
walk = RandomWalkSource(step_size=0.2)
console = ConsoleSink()

walk >> console
```

### Plugin Best Practices

1. **Namespace Your Types**: Use descriptive, unique node type names
2. **Handle Dependencies**: Check for optional dependencies gracefully
3. **Document Parameters**: Provide clear param_spec for UI generation
4. **Test Thoroughly**: Unit test nodes, integration test with engine
5. **Version Compatibility**: Specify minimum RASL version requirements
6. **Error Handling**: Fail gracefully with helpful error messages

### Plugin Distribution

**PyPI Distribution**:
```bash
# Build and upload plugin
python -m build
twine upload dist/*

# Users install with:
pip install my-rasl-plugin
```

**Git Distribution**:
```bash
# Users install directly from git
pip install git+https://github.com/user/my-rasl-plugin.git
```

## Core Plugin Extensions

### Planned Core Plugins

**Audio Plugin** (`rasl-audio`):
- AudioSource, AudioSink nodes
- FFT, Filter, Envelope transforms
- Beat detection and tempo analysis

**Lighting Plugin** (`rasl-lighting`):
- sACN, Art-Net, LIFX protocol sinks
- Color space transforms (HSV, RGB, RGBW)
- Lighting-specific effects (chase, fade, strobe)

**Video Plugin** (`rasl-video`):
- Video file sources
- Frame extraction and processing
- LED matrix mapping

**Network Plugin** (`rasl-network`):
- OSC, MQTT, WebSocket sources/sinks
- Network discovery and device management
- Protocol bridging capabilities

This plugin architecture enables RASL to grow organically while maintaining a lightweight, stable core that works reliably across all installations.
