from xrepotest.paths import get_lsp_enriched_dir, get_rag_enriched_dir, get_project_root


LSP_DATA_DIR = get_lsp_enriched_dir()
RAG_DATA_DIR = get_rag_enriched_dir()
XREPOTEST_DATA_DIR = get_project_root() / "src" / "xrepotest" / "environments" / "xrepotest"
DEFAULT_RAG_WINDOW_SIZE = 50
DEFAULT_RAG_SLICE_SIZE = 10
DEFAULT_RAG_TOP_K = 20


datapath = {
    "rust": {"file": str(XREPOTEST_DATA_DIR / "rust_functions.jsonl")},
    "go": {"file": str(XREPOTEST_DATA_DIR / "go_functions.jsonl")},
    "julia": {"file": str(XREPOTEST_DATA_DIR / "julia_functions.jsonl")},
    "ruby": {"file": str(XREPOTEST_DATA_DIR / "ruby_functions.jsonl")},
    "php": {"file": str(XREPOTEST_DATA_DIR / "php_functions.jsonl")}
}

bm_25_rag_datapath = {
    "rust": {"file": str(RAG_DATA_DIR / f"rust_functions_ws{DEFAULT_RAG_WINDOW_SIZE}_ss{DEFAULT_RAG_SLICE_SIZE}_k{DEFAULT_RAG_TOP_K}_enriched_bm25.jsonl"), "context_key": "retrieved_contexts_bm25"},
    "go": {"file": str(RAG_DATA_DIR / f"go_functions_ws{DEFAULT_RAG_WINDOW_SIZE}_ss{DEFAULT_RAG_SLICE_SIZE}_k{DEFAULT_RAG_TOP_K}_enriched_bm25.jsonl"), "context_key": "retrieved_contexts_bm25"},
    "julia": {"file": str(RAG_DATA_DIR / f"julia_functions_ws{DEFAULT_RAG_WINDOW_SIZE}_ss{DEFAULT_RAG_SLICE_SIZE}_k{DEFAULT_RAG_TOP_K}_enriched_bm25.jsonl"), "context_key": "retrieved_contexts_bm25"},
    "ruby": {"file": str(RAG_DATA_DIR / f"ruby_functions_ws{DEFAULT_RAG_WINDOW_SIZE}_ss{DEFAULT_RAG_SLICE_SIZE}_k{DEFAULT_RAG_TOP_K}_enriched_bm25.jsonl"), "context_key": "retrieved_contexts_bm25"},
    "php": {"file": str(RAG_DATA_DIR / f"php_functions_ws{DEFAULT_RAG_WINDOW_SIZE}_ss{DEFAULT_RAG_SLICE_SIZE}_k{DEFAULT_RAG_TOP_K}_enriched_bm25.jsonl"), "context_key": "retrieved_contexts_bm25"}
}

dense_rag_datapath = {
    "rust": {"file": str(RAG_DATA_DIR / f"rust_functions_ws{DEFAULT_RAG_WINDOW_SIZE}_ss{DEFAULT_RAG_SLICE_SIZE}_k{DEFAULT_RAG_TOP_K}_enriched_unixcoder.jsonl"), "context_key": "retrieved_contexts_unixcoder"},
    "go": {"file": str(RAG_DATA_DIR / f"go_functions_ws{DEFAULT_RAG_WINDOW_SIZE}_ss{DEFAULT_RAG_SLICE_SIZE}_k{DEFAULT_RAG_TOP_K}_enriched_unixcoder.jsonl"), "context_key": "retrieved_contexts_unixcoder"},
    "julia": {"file": str(RAG_DATA_DIR / f"julia_functions_ws{DEFAULT_RAG_WINDOW_SIZE}_ss{DEFAULT_RAG_SLICE_SIZE}_k{DEFAULT_RAG_TOP_K}_enriched_unixcoder.jsonl"), "context_key": "retrieved_contexts_unixcoder"},
    "ruby": {"file": str(RAG_DATA_DIR / f"ruby_functions_ws{DEFAULT_RAG_WINDOW_SIZE}_ss{DEFAULT_RAG_SLICE_SIZE}_k{DEFAULT_RAG_TOP_K}_enriched_unixcoder.jsonl"), "context_key": "retrieved_contexts_unixcoder"},
    "php": {"file": str(RAG_DATA_DIR / f"php_functions_ws{DEFAULT_RAG_WINDOW_SIZE}_ss{DEFAULT_RAG_SLICE_SIZE}_k{DEFAULT_RAG_TOP_K}_enriched_unixcoder.jsonl"), "context_key": "retrieved_contexts_unixcoder"}
}

lsp_datapath = {
    "rust": {"file": str(LSP_DATA_DIR / "rust_functions_enriched.jsonl")},
    "go": {"file": str(LSP_DATA_DIR / "go_functions_enriched.jsonl")},
    "julia": {"file": str(LSP_DATA_DIR / "julia_functions_enriched.jsonl")},
    "ruby": {"file": str(LSP_DATA_DIR / "ruby_functions_enriched.jsonl")},
    "php": {"file": str(LSP_DATA_DIR / "php_functions_enriched.jsonl")}
}


def get_rag_datapath(language, context_size, step_size=10, top_k=20, rag_type='bm25'):
    """
    Construct RAG file path dynamically based on parameters.
    
    Args:
        language: Language name (e.g., 'rust', 'go', 'julia', 'ruby', 'php')
        context_size: Window size (e.g., 30, 50, 70)
        step_size: Step size (default: 10)
        top_k: Top-k value used during RAG retrieval (default: 20)
        rag_type: 'bm25' or 'dense' (unixcoder)
    
    Returns:
        dict: {"file": path, "context_key": key_name}
    
    Example:
        >>> get_rag_datapath('rust', 50, 10, 20, 'bm25')
        {'file': '.../rust_functions_ws50_ss10_k20_enriched_bm25.jsonl', 
         'context_key': 'retrieved_contexts_bm25'}
    """
    lang_lower = language.lower()
    if rag_type == "bm25":
        filename = f"{lang_lower}_functions_ws{context_size}_ss{step_size}_k{top_k}_enriched_bm25.jsonl"
        context_key = "retrieved_contexts_bm25"
    else:
        filename = f"{lang_lower}_functions_ws{context_size}_ss{step_size}_k{top_k}_enriched_unixcoder.jsonl"
        context_key = "retrieved_contexts_unixcoder"
    
    return {
        "file": str(RAG_DATA_DIR / filename),
        "context_key": context_key
    }
