from experiments.evaluation.generation.prompts import constants
from xrepotest.paths import get_project_root


def test_uses_lsp_phase_output_dir():
    expected_dir = get_project_root() / "data" / "enriched" / "lsp"
    assert constants.LSP_DATA_DIR == expected_dir
    assert constants.lsp_datapath["go"]["file"] == str(expected_dir / "go_functions_enriched.jsonl")


def test_uses_rag_phase_output_dir():
    expected_dir = get_project_root() / "data" / "enriched" / "rag"
    assert constants.RAG_DATA_DIR == expected_dir
    assert constants.bm_25_rag_datapath["go"]["file"] == str(expected_dir / "go_functions_ws50_ss10_k20_enriched_bm25.jsonl")


def test_get_rag_datapath_uses_rag_output_dir():
    data = constants.get_rag_datapath("rust", 50, step_size=10, top_k=20, rag_type="dense")

    expected_file = get_project_root() / "data" / "enriched" / "rag" / "rust_functions_ws50_ss10_k20_enriched_unixcoder.jsonl"
    assert data["file"] == str(expected_file)
    assert data["context_key"] == "retrieved_contexts_unixcoder"
