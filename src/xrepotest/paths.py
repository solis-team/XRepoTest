"""
Centralized path resolution for the xrepotest project.

All paths are resolved relative to the project root (the directory containing
pyproject.toml), so scripts work correctly regardless of the working directory
from which they are invoked.
"""

from pathlib import Path

# Directory names
REPO_DATA_DIR = "repo_data"
DATASET_DIR = "xrepotest_dataset"


def get_project_root() -> Path:
    """Return the project root directory (the directory containing pyproject.toml)."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError(
        "Could not find project root: no pyproject.toml found in any parent directory "
        f"of {__file__}"
    )


def get_repo_data_dir() -> Path:
    """Return the consolidated repo_data directory at the project root."""
    return get_project_root() / REPO_DATA_DIR


def get_data_dir() -> Path:
    """Return the shared project data directory at the project root."""
    return get_project_root() / "data"


def get_enriched_data_dir() -> Path:
    """Return the root directory for unified enriched JSONL artifacts."""
    return get_data_dir() / "enriched"


def get_lsp_enriched_dir() -> Path:
    """Return the canonical LSP-enriched output directory."""
    return get_enriched_data_dir() / "lsp"


def get_rag_enriched_dir() -> Path:
    """Return the canonical RAG-enriched output directory."""
    return get_enriched_data_dir() / "rag"


def get_evaluation_data_dir() -> Path:
    """Return the canonical experiment evaluation data directory."""
    return get_project_root() / "src" / "experiments" / "evaluation" / "data"
