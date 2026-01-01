"""
Backend v2 - LangGraph v3 Orchestration

This package contains the LangGraph-based orchestration system for AI DJ v3.

Modules:
- state.py - DJStateV3 TypedDict and helpers
- types.py - Shared dataclasses and types
- runtime.py - Graph compilation and APIs
- graphs/ - Subgraph implementations
- rag/ - Vector index and retrieval
- memory/ - Long-term store wrapper
"""

__all__ = [
    "state",
    "types",
    "runtime",
]
