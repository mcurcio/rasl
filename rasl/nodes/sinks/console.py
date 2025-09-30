"""
Console and logging sink implementations for debugging and monitoring.
"""

import json
import logging
import random
from typing import Any, Dict, Mapping, Optional

from rasl.core.nodes import BaseSink, NDArrayLike
from rasl.core.types import Frame, Schema, Component, Channel, Range


class ConsoleSink(BaseSink):
    """
    Debug sink that prints data to console with configurable formatting.
    
    Essential for development and debugging - provides real-time visual
    feedback of data flowing through the graph.
    """
    
    TYPE = "ConsoleSink"
    
    def __init__(
        self,
        *,
        format: str = "table",  # "table", "json", "raw", "summary"
        max_channels: int = 16,  # Limit output for readability
        precision: int = 3,      # Decimal places
        update_interval: float = 1.0,  # Throttle output (seconds)
        show_frame_info: bool = True,
        color_output: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.format = format
        self.max_channels = max_channels
        self.precision = precision
        self.update_interval = update_interval
        self.show_frame_info = show_frame_info
        self.color_output = color_output
        self.last_output_time = 0.0
    
    def param_spec(self) -> Mapping[str, Mapping[str, Any]]:
        return {
            "format": {
                "type": "str",
                "default": "table",
                "enum": ["table", "json", "raw", "summary"],
                "description": "Output format style"
            },
            "max_channels": {
                "type": "int",
                "default": 16,
                "min": 1,
                "max": 1000,
                "description": "Maximum channels to display"
            },
            "precision": {
                "type": "int",
                "default": 3,
                "min": 0,
                "max": 10,
                "description": "Decimal places to show"
            },
            "update_interval": {
                "type": "float",
                "default": 1.0,
                "min": 0.1,
                "max": 60.0,
                "description": "Seconds between updates"
            },
            "show_frame_info": {
                "type": "bool",
                "default": True,
                "description": "Show frame timing information"
            },
            "color_output": {
                "type": "bool",
                "default": True,
                "description": "Use colored output"
            }
        }
    
    def emit(self, frame: Frame, **inputs: NDArrayLike) -> None:
        """Print data to console with throttling."""
        # Throttle output to avoid spam
        if frame.t - self.last_output_time < self.update_interval:
            return
        
        self.last_output_time = frame.t
        
        if self.format == "table":
            self._print_table(frame, inputs)
        elif self.format == "json":
            self._print_json(frame, inputs)
        elif self.format == "summary":
            self._print_summary(frame, inputs)
        else:  # raw
            self._print_raw(frame, inputs)
    
    def _print_table(self, frame: Frame, inputs: Dict[str, NDArrayLike]):
        """Print data in table format."""
        if self.show_frame_info:
            print(f"\n{'='*60}")
            print(f"Frame {frame.seq:6d} | t={frame.t:8.3f}s | dt={frame.dt*1000:5.1f}ms")
            print(f"{'='*60}")
        
        for port_name, data in inputs.items():
            # Convert to list for consistent handling
            if hasattr(data, '__iter__') and not isinstance(data, str):
                data_list = list(data)
            else:
                data_list = [data]
            
            channels = min(len(data_list), self.max_channels)
            
            print(f"\n{port_name}:")
            print(f"  Shape: ({len(data_list)},)")
            
            if data_list:
                data_min = min(data_list)
                data_max = max(data_list)
                print(f"  Range: [{data_min:.{self.precision}f}, {data_max:.{self.precision}f}]")
            
            print(f"  Data:  [", end="")
            
            for i in range(channels):
                value = data_list[i]
                if self.color_output and isinstance(value, (int, float)) and 0 <= value <= 1:
                    # Simple color coding for 0-1 values
                    if value < 0.1:
                        color = "\033[90m"  # Dark gray
                    elif value < 0.5:
                        color = "\033[93m"  # Yellow
                    else:
                        color = "\033[92m"  # Green
                    print(f"{color}{value:.{self.precision}f}\033[0m", end="")
                else:
                    print(f"{value:.{self.precision}f}", end="")
                
                if i < channels - 1:
                    print(", ", end="")
            
            if len(data_list) > self.max_channels:
                print(f", ... +{len(data_list) - self.max_channels} more", end="")
            print("]")
    
    def _print_json(self, frame: Frame, inputs: Dict[str, NDArrayLike]):
        """Print data in JSON format."""
        output = {
            "frame": {
                "seq": frame.seq,
                "t": frame.t,
                "dt": frame.dt
            },
            "data": {}
        }
        
        for port_name, data in inputs.items():
            if hasattr(data, '__iter__') and not isinstance(data, str):
                data_list = list(data)[:self.max_channels]
            else:
                data_list = [data]
            
            output["data"][port_name] = [
                round(float(x), self.precision) for x in data_list
            ]
        
        print(json.dumps(output, indent=2))
    
    def _print_summary(self, frame: Frame, inputs: Dict[str, NDArrayLike]):
        """Print compact summary format."""
        print(f"Frame {frame.seq:6d} | ", end="")
        
        for port_name, data in inputs.items():
            if hasattr(data, '__iter__') and not isinstance(data, str):
                data_list = list(data)
                if data_list:
                    mean_val = sum(data_list) / len(data_list)
                    std_val = (sum((x - mean_val) ** 2 for x in data_list) / len(data_list)) ** 0.5
                    print(f"{port_name}[{len(data_list)}]: "
                          f"{mean_val:.{self.precision}f}±{std_val:.{self.precision}f} ", end="")
                else:
                    print(f"{port_name}[0]: empty ", end="")
            else:
                print(f"{port_name}: {data:.{self.precision}f} ", end="")
        
        print()
    
    def _print_raw(self, frame: Frame, inputs: Dict[str, NDArrayLike]):
        """Print raw data format."""
        if self.show_frame_info:
            print(f"Frame {frame.seq}: t={frame.t:.3f}, dt={frame.dt:.3f}")
        
        for port_name, data in inputs.items():
            print(f"{port_name}: {data}")
    
    def port_schema(self, name: str) -> Schema:
        """
        ConsoleSink accepts any input schema - it's flexible.
        
        Returns a minimal schema that will be compatible with any input
        through the connection validation process.
        """
        if name == "in":
            # Return an empty schema that will be adapted during connection
            # The actual schema compatibility will be handled by allowing
            # any number of channels in the connection validation
            return Schema(components=())
        
        raise ValueError(f"Unknown port: {name}")


class LoggingSink(BaseSink):
    """
    Sink that writes structured data to Python logging system.
    
    Integrates with standard Python logging for production monitoring
    and structured data collection.
    """
    
    TYPE = "LoggingSink"
    
    def __init__(
        self,
        *,
        logger_name: str = "rasl.data",
        level: int = logging.INFO,
        include_data: bool = False,  # Log actual values or just metadata
        sample_rate: float = 1.0,    # Fraction of frames to log
        **kwargs
    ):
        super().__init__(**kwargs)
        self.logger = logging.getLogger(logger_name)
        self.level = level
        self.include_data = include_data
        self.sample_rate = sample_rate
    
    def param_spec(self) -> Mapping[str, Mapping[str, Any]]:
        return {
            "logger_name": {
                "type": "str",
                "default": "rasl.data",
                "description": "Python logger name to use"
            },
            "level": {
                "type": "int",
                "default": logging.INFO,
                "description": "Logging level (10=DEBUG, 20=INFO, etc.)"
            },
            "include_data": {
                "type": "bool",
                "default": False,
                "description": "Include actual data values in logs"
            },
            "sample_rate": {
                "type": "float",
                "default": 1.0,
                "min": 0.0,
                "max": 1.0,
                "description": "Fraction of frames to log (0.1 = 10%)"
            }
        }
    
    def emit(self, frame: Frame, **inputs: NDArrayLike) -> None:
        """Log data with sampling."""
        if random.random() > self.sample_rate:
            return
        
        log_data = {
            "frame": frame.seq,
            "time": frame.t,
            "dt": frame.dt,
            "ports": {}
        }
        
        for port_name, data in inputs.items():
            # Convert to consistent format
            if hasattr(data, '__iter__') and not isinstance(data, str):
                data_list = list(data)
            else:
                data_list = [data]
            
            port_info = {
                "length": len(data_list),
                "type": type(data).__name__
            }
            
            if data_list:
                try:
                    numeric_data = [float(x) for x in data_list]
                    port_info.update({
                        "min": min(numeric_data),
                        "max": max(numeric_data),
                        "mean": sum(numeric_data) / len(numeric_data)
                    })
                    
                    if len(numeric_data) > 1:
                        mean = port_info["mean"]
                        variance = sum((x - mean) ** 2 for x in numeric_data) / len(numeric_data)
                        port_info["std"] = variance ** 0.5
                    
                    # Include actual data for small arrays or if requested
                    if self.include_data and len(data_list) <= 32:
                        port_info["values"] = numeric_data
                        
                except (ValueError, TypeError):
                    # Non-numeric data
                    if self.include_data:
                        port_info["values"] = data_list[:32]  # Limit size
            
            log_data["ports"][port_name] = port_info
        
        self.logger.log(self.level, "Frame data", extra={"rasl_data": log_data})
    
    def port_schema(self, name: str) -> Schema:
        """Accept any input schema."""
        if name == "in":
            return Schema(components=(
                Component(
                    name="Any",
                    channels=(Channel("data", "unitless", Range()),)
                ),
            ))
        
        raise ValueError(f"Unknown port: {name}")
