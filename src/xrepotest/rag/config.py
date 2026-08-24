"""RAG submodule configuration."""

RAG_DEFAULT_WINDOW_SIZE = 20
RAG_DEFAULT_SLICE_SIZE = 2
RAG_DEFAULT_TOP_K = 10
RAG_WINDOWS_CACHE_DIR = "data/cache/windows"
RAG_OUTPUT_DIR = "data/enriched/rag"

__all__ = [
    "RAG_DEFAULT_WINDOW_SIZE",
    "RAG_DEFAULT_SLICE_SIZE",
    "RAG_DEFAULT_TOP_K",
    "RAG_WINDOWS_CACHE_DIR",
    "RAG_OUTPUT_DIR",
]
