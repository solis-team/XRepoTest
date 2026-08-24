"""
RAG System for Unit Test Generation.

This package provides tools for:
- Code windowing and preprocessing
- BM25 and UniXcoder retrieval
- Pipeline orchestration for enriching xrepotest data
"""

__version__ = "1.0.0"
__author__ = "RAG Project"

from xrepotest.rag.preprocessing import (
    CodeWindowMaker,
    UnitTestWindowMaker,
    RepoWindowMaker,
    process_function_for_rag
)

from xrepotest.rag.retrieval import (
    BM25Retriever,
    UniXcoderRetriever,
    process_with_bm25,
    process_with_unixcoder
)

from xrepotest.rag.utils import (
    FileTools,
    FilePathBuilder,
    format_retrieval_prompt
)

from xrepotest.rag.pipeline import RAGPipeline

__all__ = [
    # Preprocessing
    'CodeWindowMaker',
    'UnitTestWindowMaker',
    'RepoWindowMaker',
    'process_function_for_rag',
    # Retrieval
    'BM25Retriever',
    'UniXcoderRetriever',
    'process_with_bm25',
    'process_with_unixcoder',
    # Utils
    'FileTools',
    'FilePathBuilder',
    'format_retrieval_prompt',
    # Pipeline
    'RAGPipeline'
]
