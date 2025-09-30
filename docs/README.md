# RASL Documentation

Welcome to the RASL (Real-Time Animation Show Library) documentation. This collection of documents provides comprehensive guidance for understanding, using, and extending RASL.

## Documentation Structure

### Getting Started
- **[Overview](overview.md)** - High-level introduction to RASL's concepts and philosophy
- **[User Guide](user-guide.md)** - Step-by-step guide to creating your first animations
- **[API Reference](api.md)** - Complete interface specifications and type definitions

### Core Architecture
- **[Time and Liveness](time-and-liveness.md)** - Understanding execution modes, time domains, and source lifecycles
- **[Graph Model](graph.md)** - How nodes connect, data flows, and validation works
- **[Execution Engine](execution-engine.md)** - Scheduler, executor, validator, and monitoring systems

### Development Guides
- **[Node Development](node-development.md)** - Creating custom sources, transforms, and sinks
- **[Plugin System](plugin-system.md)** - Extending RASL with plugins and maintaining compatibility
- **[Web API](web-api.md)** - REST/WebSocket APIs for monitoring and control

### Advanced Topics
- **[Export System](export-system.md)** - Offline rendering and format interoperability

## Quick Navigation

### For Users
Start with the **[Overview](overview.md)** to understand RASL's approach, then follow the **[User Guide](user-guide.md)** to create your first animation. The **[API Reference](api.md)** provides details on all available nodes and functions.

### For Developers
Begin with **[Node Development](node-development.md)** to understand the base class architecture and mixin system. The **[Execution Engine](execution-engine.md)** document explains how the core engine works. For extending functionality, see **[Plugin System](plugin-system.md)**.

### For Integrators  
The **[Web API](web-api.md)** document details REST and WebSocket interfaces for building custom UIs or integrating with other systems. **[Export System](export-system.md)** covers offline rendering and format compatibility.

### For Architects
**[Time and Liveness](time-and-liveness.md)** explains RASL's execution model and how it differs from timeline-based sequencers. **[Graph Model](graph.md)** covers the DAG execution and validation system.

## Key Concepts Quick Reference

### Execution Modes
- **DETERMINISTIC**: Pure finite sources → predictable duration, export possible
- **CONTROLLABLE**: Finite + generator sources → user-controlled duration, export possible
- **LIVE**: Any streaming sources → real-time only, no export

### Source Liveness Types
- **FINITE**: Bounded media with definite end (CSV file, audio file played once)
- **GENERATOR**: Can produce data indefinitely but may end naturally (sine wave, noise)
- **STREAMING**: External, potentially infinite streams (network input, live audio)

### Node Types
- **Source**: Data generators with output ports only
- **Transform**: Data processors with input and output ports
- **Sink**: Output handlers with input ports only

### Time Model
- **Sequence Time**: Primary time reference (t=0.0 at start)
- **Frame**: `{t, dt, seq}` time reference for all nodes
- **Time Domain Bridging**: Explicit conversion between different time references

## Architecture Principles

### Separation of Concerns
- **Base Classes**: Handle engine integration, lifecycle, error propagation
- **Child Classes**: Focus purely on domain logic and algorithms
- **Mixins**: Provide composable behaviors (looping, duration, rate limiting)

### Explicit Over Magic
- **Time domain conversions** are visible nodes, not hidden engine behavior
- **Looping behavior** is explicit in source configuration
- **Error handling** distinguishes between EOS (silent) and errors (noisy)

### Real-time Performance
- **Lazy evaluation**: Nodes compute only when sinks demand data
- **Per-frame memoization**: Shared subgraphs compute once per frame
- **Frame budgets**: Configurable timing constraints for real-time operation

## Contributing

### Documentation Updates
Documentation is written in Markdown and should be kept up-to-date with code changes. Each document focuses on a specific domain to maintain clarity and avoid overwhelming detail.

### Code Examples
All code examples in documentation should be:
- **Runnable**: Can be executed as-is or with minimal setup
- **Realistic**: Demonstrate actual use cases, not toy examples
- **Well-commented**: Explain the important concepts being illustrated

### Cross-References
Documents should link to related concepts in other documents to help readers navigate the architecture. Use relative links to maintain portability.

## Version Information

This documentation corresponds to RASL version 0.1.0 and reflects the target architecture. Some features may not yet be implemented - check the main README.md for current implementation status.

## Getting Help

- **GitHub Issues**: Report bugs or request features
- **Discussions**: Ask questions about usage or architecture
- **Examples**: See the `examples/` directory for working code samples

The documentation is designed to grow with RASL - as new features are added and the architecture evolves, these documents will be updated to reflect the current state and best practices.
