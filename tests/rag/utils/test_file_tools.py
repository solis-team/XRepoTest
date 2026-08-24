import json
import os

from xrepotest.rag.utils.file_tools import FilePathBuilder, FileTools


def test_load_jsonl_reads_non_empty_lines(tmp_path):
    path = tmp_path / "data.jsonl"
    path.write_text(
        '\n{"a": 1}\n\n{"b": "x"}\n',
        encoding="utf-8",
    )

    result = FileTools.load_jsonl(str(path))

    assert result == [{"a": 1}, {"b": "x"}]


def test_save_jsonl_creates_parent_dirs_and_writes_valid_jsonl(tmp_path):
    target = tmp_path / "nested" / "dir" / "rows.jsonl"
    payload = [{"k": 1}, {"emoji": "😀"}]

    FileTools.save_jsonl(payload, str(target))

    assert target.exists()
    lines = target.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == payload


def test_iterate_repository_filters_extensions_and_skips_excluded_dirs(tmp_path):
    base_dir = tmp_path
    repo_name = "repo1"
    repo_root = base_dir / repo_name
    (repo_root / "src").mkdir(parents=True)
    (repo_root / ".git").mkdir()
    (repo_root / "node_modules").mkdir()

    (repo_root / "src" / "keep.py").write_text("print('ok')", encoding="utf-8")
    (repo_root / "src" / "skip.txt").write_text("text", encoding="utf-8")
    (repo_root / ".git" / "hidden.py").write_text("bad", encoding="utf-8")
    (repo_root / "node_modules" / "pkg.js").write_text("bad", encoding="utf-8")

    result = FileTools.iterate_repository(
        repo_name=repo_name,
        base_dir=str(base_dir),
        extensions=(".py",),
    )

    assert set(result.keys()) == {(repo_name, "src", "keep.py")}
    assert result[(repo_name, "src", "keep.py")] == "print('ok')"


def test_file_path_builder_helpers_build_expected_paths():
    base = os.path.join("root", "workspace")
    builder = FilePathBuilder(base_dir=base)

    assert builder.get_repo_path("repo", "repos") == os.path.join(base, "repos", "repo")
    assert builder.get_cache_path("a", "b.jsonl") == os.path.join(base, "data", "cache", "a", "b.jsonl")
    assert builder.get_temp_path("x.tmp") == os.path.join(base, "data", "temp", "x.tmp")
    assert builder.get_results_path("run1", "out.json") == os.path.join(base, "data", "results", "run1", "out.json")
