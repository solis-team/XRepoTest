import json

from xrepotest.rag.utils.prompt_formatter import (
    format_retrieval_prompt,
    load_and_filter_chunks,
)


def test_format_retrieval_prompt_orders_modules_and_appends_target_prompt():
    input_fpath_tuple = ("repo", "src", "current.py")
    target_prompt = "def target_fn(x):"
    top_chunks = [
        {"context": "helper_a()", "metadata": [{"fpath_tuple": ("repo", "src", "helpers.py")}]},
        {"context": "current_impl()", "metadata": [{"fpath_tuple": input_fpath_tuple}]},
        {"context": "util_b()", "metadata": [{"fpath_tuple": ("repo", "src", "utils.py")}]},
    ]

    prompt = format_retrieval_prompt(top_chunks, input_fpath_tuple, target_prompt)

    assert "#FILE: repo/src/helpers.py" in prompt
    assert "#FILE: repo/src/utils.py" in prompt
    assert "#CURRENT FILE: repo/src/current.py" in prompt

    current_idx = prompt.index("#CURRENT FILE: repo/src/current.py")
    helpers_idx = prompt.index("#FILE: repo/src/helpers.py")
    utils_idx = prompt.index("#FILE: repo/src/utils.py")
    assert helpers_idx < current_idx
    assert utils_idx < current_idx

    assert prompt.rstrip().endswith(target_prompt)


def test_load_and_filter_chunks_with_imported_context_filters_repo_windows(tmp_path):
    input_fpath_tuple = ["repo", "src", "current.py"]
    import_file_tuples = [["repo", "src", "helpers.py"]]

    windows_path = tmp_path / "repo_windows.jsonl"
    current_fpath = tmp_path / "current_windows.jsonl"

    repo_rows = [
        {"context": "keep single import", "metadata": [{"fpath_tuple": ["repo", "src", "helpers.py"]}]},
        {"context": "drop current single", "metadata": [{"fpath_tuple": input_fpath_tuple}]},
        {"context": "drop not-import single", "metadata": [{"fpath_tuple": ["repo", "src", "other.py"]}]},
        {
            "context": "keep filtered multi",
            "metadata": [
                {"fpath_tuple": ["repo", "src", "other.py"]},
                {"fpath_tuple": ["repo", "src", "helpers.py"]},
                {"fpath_tuple": input_fpath_tuple},
            ],
        },
    ]
    current_rows = [{"context": "current window", "metadata": [{"fpath_tuple": ("wrong",)}]}]

    windows_path.write_text("\n".join(json.dumps(r) for r in repo_rows) + "\n", encoding="utf-8")
    current_fpath.write_text("\n".join(json.dumps(r) for r in current_rows) + "\n", encoding="utf-8")

    result = load_and_filter_chunks(
        windows_path=str(windows_path),
        current_fpath=str(current_fpath),
        input_fpath_tuple=input_fpath_tuple,
        import_file_tuples=import_file_tuples,
        imported_context=True,
    )

    assert [item["context"] for item in result] == [
        "keep single import",
        "keep filtered multi",
        "current window",
    ]
    assert result[1]["metadata"] == [{"fpath_tuple": ["repo", "src", "helpers.py"]}]
    assert result[-1]["metadata"] == [{"fpath_tuple": input_fpath_tuple}]


def test_load_and_filter_chunks_without_imported_context_keeps_all_non_current(tmp_path):
    input_fpath_tuple = ["repo", "src", "current.py"]

    windows_path = tmp_path / "repo_windows.jsonl"
    current_fpath = tmp_path / "current_windows.jsonl"

    repo_rows = [
        {"context": "keep single other", "metadata": [{"fpath_tuple": ["repo", "src", "helpers.py"]}]},
        {"context": "drop current single", "metadata": [{"fpath_tuple": input_fpath_tuple}]},
        {
            "context": "keep filtered multi",
            "metadata": [
                {"fpath_tuple": input_fpath_tuple},
                {"fpath_tuple": ["repo", "src", "other.py"]},
            ],
        },
    ]
    current_rows = [{"context": "current window", "metadata": []}]

    windows_path.write_text("\n".join(json.dumps(r) for r in repo_rows) + "\n", encoding="utf-8")
    current_fpath.write_text("\n".join(json.dumps(r) for r in current_rows) + "\n", encoding="utf-8")

    result = load_and_filter_chunks(
        windows_path=str(windows_path),
        current_fpath=str(current_fpath),
        input_fpath_tuple=input_fpath_tuple,
        import_file_tuples=[],
        imported_context=False,
    )

    assert [item["context"] for item in result] == [
        "keep single other",
        "keep filtered multi",
        "current window",
    ]
    assert result[1]["metadata"] == [{"fpath_tuple": ["repo", "src", "other.py"]}]
    assert result[-1]["metadata"] == [{"fpath_tuple": input_fpath_tuple}]
