from xrepotest import paths


def test_get_project_root_finds_repo_root_with_pyproject():
    root = paths.get_project_root()

    assert (root / "pyproject.toml").exists()


def test_get_repo_data_dir_appends_repo_data_to_project_root():
    expected = paths.get_project_root() / "repo_data"
    assert paths.get_repo_data_dir() == expected


def test_get_data_dir_appends_data_to_project_root():
    expected = paths.get_project_root() / "data"
    assert paths.get_data_dir() == expected


def test_get_enriched_data_dir_points_to_unified_enriched_root():
    expected = paths.get_project_root() / "data" / "enriched"
    assert paths.get_enriched_data_dir() == expected


def test_get_lsp_enriched_dir_points_to_lsp_subdirectory():
    expected = paths.get_project_root() / "data" / "enriched" / "lsp"
    assert paths.get_lsp_enriched_dir() == expected


def test_get_rag_enriched_dir_points_to_rag_subdirectory():
    expected = paths.get_project_root() / "data" / "enriched" / "rag"
    assert paths.get_rag_enriched_dir() == expected
