"""
Configuration management for RASL application.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """Application configuration."""
    
    # Script and execution
    script_path: Path
    watch_enabled: bool = True
    debug_mode: bool = False
    
    # Server configuration
    host: str = "localhost"
    ui_port: int = 8080
    api_port: int = 8081
    
    # Engine configuration
    default_frame_rate: float = 30.0
    max_frame_rate: float = 1000.0
    frame_budget_ms: float = 16.0  # ~60 FPS budget
    
    # Monitoring configuration
    metrics_retention_seconds: float = 300.0  # 5 minutes
    health_check_interval: float = 1.0
    
    # Hot-reload configuration
    reload_debounce_ms: int = 500
    
    # Security (for future use)
    enable_auth: bool = False
    api_key: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        # TODO: Implement environment variable loading
        # This would read from RASL_* environment variables
        return cls(script_path=Path("script.py"))
        
    def validate(self) -> None:
        """Validate configuration values."""
        if not self.script_path.exists():
            raise ValueError(f"Script path does not exist: {self.script_path}")
            
        if self.ui_port == self.api_port:
            raise ValueError("UI port and API port cannot be the same")
            
        if self.default_frame_rate <= 0 or self.default_frame_rate > self.max_frame_rate:
            raise ValueError(f"Invalid frame rate: {self.default_frame_rate}")
            
        if self.frame_budget_ms <= 0:
            raise ValueError(f"Invalid frame budget: {self.frame_budget_ms}ms")
