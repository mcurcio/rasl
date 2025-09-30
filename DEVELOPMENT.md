# RASL Development Setup

This document covers setting up a development environment for RASL using `uv` for fast, reliable Python package management.

## Prerequisites

- Python 3.9 or higher
- [uv](https://github.com/astral-sh/uv) - Ultra-fast Python package installer

### Install uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or via pip
pip install uv
```

## Quick Start

```bash
# Clone and setup development environment
git clone <repository-url>
cd rasl

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Verify installation
rasl --help
```

## Development Environment

### Virtual Environment Setup

```bash
# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate     # Windows

# Install RASL in editable mode with dev dependencies
uv pip install -e ".[dev]"
```

### Dependency Management

The project uses `pyproject.toml` for dependency management:

- **Core dependencies**: Required for RASL runtime
- **Dev dependencies**: Testing, linting, type checking
- **Build dependencies**: For creating standalone executables

```bash
# Install only core dependencies
uv pip install -e .

# Install with dev dependencies (recommended for development)
uv pip install -e ".[dev]"

# Install with build dependencies
uv pip install -e ".[build]"

# Install all optional dependencies
uv pip install -e ".[dev,build]"
```

### Adding New Dependencies

```bash
# Add a new core dependency
uv add package-name

# Add a new dev dependency
uv add --dev package-name

# Add with version constraints
uv add "package-name>=1.0.0,<2.0.0"
```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/integration/test_engine_execution.py

# Run with coverage
pytest --cov=rasl --cov-report=html

# Run only fast tests (exclude slow integration tests)
pytest -m "not slow"
```

### Code Quality

```bash
# Format code
black rasl/ tests/
isort rasl/ tests/

# Lint code
ruff check rasl/ tests/

# Type checking
mypy rasl/

# Run all quality checks
./scripts/check-quality.sh  # (if exists)
```

### Running RASL

```bash
# Run example script
rasl run examples/simple_sine.py

# Validate script without running
rasl validate examples/simple_sine.py

# Start web server only
rasl serve --port 8080

# Enable debug logging
RASL_LOG_LEVEL=DEBUG rasl run examples/simple_sine.py
```

## Project Structure

```
rasl/
├── rasl/                   # Main package
│   ├── core/              # Core engine components
│   ├── nodes/             # Node implementations
│   ├── server/            # Web server and API
│   ├── script/            # Script loading system
│   └── ui/                # Web interface assets
├── tests/                 # Test suite
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── fixtures/          # Test data and scripts
├── examples/              # Example scripts
├── docs/                  # Documentation
└── scripts/               # Development scripts
```

## Environment Variables

```bash
# Logging level (DEBUG, INFO, WARNING, ERROR)
export RASL_LOG_LEVEL=DEBUG

# Default frame rate for execution
export RASL_DEFAULT_FPS=60

# Web server configuration
export RASL_HOST=localhost
export RASL_PORT=8080

# Hardware protocol settings
export RASL_SACN_UNIVERSE=1
export RASL_LIFX_BROADCAST_IP=255.255.255.255
```

## IDE Configuration

### VS Code

Create `.vscode/settings.json`:

```json
{
    "python.defaultInterpreterPath": "./.venv/bin/python",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests/"],
    "python.linting.enabled": true,
    "python.linting.ruffEnabled": true,
    "python.formatting.provider": "black",
    "editor.formatOnSave": true,
    "python.sortImports.args": ["--profile", "black"]
}
```

### PyCharm

1. Open project in PyCharm
2. Go to Settings → Project → Python Interpreter
3. Add interpreter → Existing environment
4. Select `.venv/bin/python`
5. Enable pytest as test runner in Settings → Tools → Python Integrated Tools

## Troubleshooting

### Common Issues

**Import errors when running tests:**
```bash
# Make sure RASL is installed in editable mode
uv pip install -e .
```

**uv not found:**
```bash
# Make sure uv is in your PATH
echo $PATH
# Reinstall uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Virtual environment activation issues:**
```bash
# Recreate virtual environment
rm -rf .venv
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

**Hardware protocol errors:**
```bash
# Install optional hardware dependencies
uv pip install sacn lifxlan

# Check network permissions (sACN requires multicast)
# May need to run with sudo on some systems
```

### Performance Issues

**Slow test execution:**
```bash
# Run tests in parallel
pytest -n auto  # Requires pytest-xdist

# Skip slow tests during development
pytest -m "not slow"
```

**High memory usage:**
```bash
# Monitor memory usage during development
# Consider using smaller test datasets
# Profile with memory_profiler if needed
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Set up development environment: `uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"`
4. Make your changes
5. Run tests: `pytest`
6. Run quality checks: `black . && isort . && ruff check . && mypy rasl/`
7. Commit changes: `git commit -m 'Add amazing feature'`
8. Push to branch: `git push origin feature/amazing-feature`
9. Open a Pull Request

## Resources

- [uv Documentation](https://github.com/astral-sh/uv)
- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [RASL Architecture Documentation](docs/architecture.md)
