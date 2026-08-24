import json

import pytest

from xrepotest.crawler.repo_scanner import RepositoryScanner


@pytest.fixture
def scanner_config_path(tmp_path):
    config = {
        "file_extensions": {"Go": [".go"], "Rust": [".rs"]},
        "test_patterns": {
            "exclude_paths": ["tests/", "spec/"],
            "exclude_files": ["_test.", ".spec."],
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


def test_is_test_file_matches_excluded_paths_and_files(scanner_config_path):
    scanner = RepositoryScanner(str(scanner_config_path))

    assert scanner.is_test_file("/repo/tests/unit/main.go") is True
    assert scanner.is_test_file("/repo/spec/api/main.go") is True
    assert scanner.is_test_file("/repo/src/math_test.go") is True
    assert scanner.is_test_file("/repo/src/math.spec.go") is True
    assert scanner.is_test_file("/repo/src/math.go") is False


def test_get_source_files_filters_extensions_and_excludes_test_files(
    tmp_path, scanner_config_path
):
    scanner = RepositoryScanner(str(scanner_config_path))
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()

    (repo / "src" / "main.go").write_text("package main", encoding="utf-8")
    (repo / "src" / "util.go").write_text("package main", encoding="utf-8")
    (repo / "src" / "util_test.go").write_text("package main", encoding="utf-8")
    (repo / "tests" / "integration.go").write_text("package main", encoding="utf-8")
    (repo / "src" / "lib.rs").write_text("fn main() {}", encoding="utf-8")
    (repo / "src" / "note.txt").write_text("ignore", encoding="utf-8")

    source_files = scanner.get_source_files(str(repo), "go")

    assert set(source_files) == {
        str(repo / "src" / "main.go"),
        str(repo / "src" / "util.go"),
    }


def test_scan_repo_directory_returns_language_repo_tuples_with_lowercase_language(
    tmp_path, scanner_config_path
):
    scanner = RepositoryScanner(str(scanner_config_path))
    base = tmp_path / "repos"
    (base / "Go" / "repo_one").mkdir(parents=True)
    (base / "RUST" / "repo_two").mkdir(parents=True)
    (base / "Go" / "README.md").write_text("not a repo dir", encoding="utf-8")

    repos = scanner.scan_repo_directory(str(base))

    assert set(repos) == {
        ("go", str(base / "Go" / "repo_one"), "repo_one"),
        ("rust", str(base / "RUST" / "repo_two"), "repo_two"),
    }
