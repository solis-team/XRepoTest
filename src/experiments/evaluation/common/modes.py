"""Evaluation mode constants and groups."""

# Core Modes
DEFAULT_PROMPT_MODE = "standard"
LSP_DATA_MODE = "lsp_context"
FILE_CONTEXT_MODE = "file_context"

# RAG Modes Group
RAG_MODES = frozenset({"rag_bm25", "rag_dense"})

# Combine all valid modes for CLI validation and routing
PROMPT_MODE_CHOICES = (
    DEFAULT_PROMPT_MODE,
    LSP_DATA_MODE,
    FILE_CONTEXT_MODE,
    *sorted(list(RAG_MODES)),
)

__all__ = [
    "DEFAULT_PROMPT_MODE",
    "LSP_DATA_MODE",
    "FILE_CONTEXT_MODE",
    "RAG_MODES",
    "PROMPT_MODE_CHOICES",
]
