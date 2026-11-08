"""Official-compatible client SDK for the deployed Closed-Form Agentic RAG HTTP API.

The server contract and implementation live in service/; this package is a client.
"""
from .client import APIError, AsyncClosedFormRAGClient, ClosedFormRAGClient

__all__ = ["APIError", "AsyncClosedFormRAGClient", "ClosedFormRAGClient"]
__version__ = "1.0.0"
