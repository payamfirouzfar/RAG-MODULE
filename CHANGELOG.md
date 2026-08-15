# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - Step 1: Framework Kernel

### Added

- `Module`: base callable component with `forward`/`__call__` separation.
- `RAGModule`: marker base class for top-level RAG systems.
- Automatic child module registration via attribute assignment.
- `named_modules`, `named_children`, `modules`, `children` traversal.
- `Sequential` composition.
- `inspect()` architecture tree and `__repr__`.
- `RAGConfig`: immutable, explicit configuration objects.
- Framework exception hierarchy (`RAGTorchError` and subclasses).
- Lightweight `EventBus`/`Event`/`EventType` observability primitives.
- Unit, integration, and public-API contract tests.
- CI pipeline (format, lint, type check, test, build).
