from pathlib import Path

import pytest

from xrepotest import cli


def _capture_dispatch(monkeypatch):
    captured: list[dict[str, object]] = []

    def fake_run_entrypoint(entrypoint: str, argv, *, prog: str) -> int:
        captured.append(
            {
                "entrypoint": entrypoint,
                "argv": list(argv),
                "prog": prog,
            }
        )
        return 0

    monkeypatch.setattr(cli, "_run_entrypoint", fake_run_entrypoint)
    return captured


def test_cli_requires_subcommand() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main([])

    assert exc_info.value.code == 2


def test_prompts_dispatch_normalizes_language(monkeypatch) -> None:
    captured = _capture_dispatch(monkeypatch)

    exit_code = cli.main(
        [
            "prompts",
            "--split",
            "go",
            "--lang",
            "GO",
            "--output_dir",
            "out/prompts",
        ]
    )

    assert exit_code == 0
    assert captured[0]["entrypoint"] == "experiments.evaluation.generation.generate_prompts:main"
    assert captured[0]["prog"] == "xrepotest prompts"
    assert captured[0]["argv"] == [
        "--split",
        "go",
        "--lang",
        "go",
        "--output_dir",
        "out/prompts",
    ]


def test_eval_dispatch_normalizes_language(monkeypatch) -> None:
    captured = _capture_dispatch(monkeypatch)

    exit_code = cli.main(
        [
            "eval",
            "--lang",
            "GO",
            "--mode",
            "standard",
            "--model",
            "my_model",
            "--enable_mutation",
        ]
    )

    assert exit_code == 0
    assert captured[0]["entrypoint"] == "experiments.evaluation.run_evaluation:main"
    assert captured[0]["prog"] == "xrepotest eval"
    assert captured[0]["argv"] == [
        "--lang",
        "go",
        "--input_file",
        "processed.jsonl",
        "--output_file",
        "detailed_results.jsonl",
        "--mode",
        "standard",
        "--model",
        "my_model",
        "--enable_mutation",
    ]


def test_eval_rejects_unsupported_language() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["eval", "--lang", "python"])

    assert exc_info.value.code == 2


def test_run_dispatches_full_pipeline(monkeypatch) -> None:
    captured = _capture_dispatch(monkeypatch)

    exit_code = cli.main(
        [
            "run",
            "--lang",
            "go",
            "--model",
            "org/model:tag",
            "--api_key",
            "secret",
        ]
    )

    assert exit_code == 0
    assert [item["entrypoint"] for item in captured] == [
        "experiments.evaluation.generation.generate_prompts:main",
        "experiments.evaluation.generation.generate_responses:main",
        "experiments.evaluation.preprocessing.preprocess:main",
        "experiments.evaluation.run_evaluation:main",
    ]

    data_root = Path(cli.__file__).resolve().parents[1] / "experiments" / "evaluation" / "data"
    mode_dir = "standard"
    model_dir = "org_model_tag"

    assert captured[0]["argv"] == [
        "--split",
        "go",
        "--lang",
        "go",
        "--output_dir",
        str(data_root / "responses" / "go" / mode_dir),
        "--mode",
        "standard",
    ]
    assert captured[1]["argv"] == [
        "--model",
        "org/model:tag",
        "--input_dir",
        str(data_root / "responses" / "go" / mode_dir),
        "--api_base",
        cli.API_BASE_URL,

        "--max_workers",
        "20",
        "--delay",
        "0.0",
        "--max_retries",
        "3",
        "--retry_delay",
        "5.0",
        "--api_key",
        "secret",
    ]
    assert captured[2]["argv"] == [
        "--input_directory",
        str(data_root / "responses" / "go" / mode_dir / model_dir / "prompts_responses.jsonl"),
        "--output_directory",
        str(data_root / "results" / "go" / mode_dir / model_dir / "processed.jsonl"),
        "--max_tests",
        "10",
    ]
    assert captured[3]["argv"] == [
        "--lang",
        "go",
        "--input_file",
        "processed.jsonl",
        "--output_file",
        "detailed_results.jsonl",
        "--mode",
        "standard",
        "--model",
        model_dir,
    ]


def test_run_stops_on_first_failure(monkeypatch) -> None:
    captured: list[str] = []

    def fake_run_entrypoint(entrypoint: str, argv, *, prog: str) -> int:
        captured.append(entrypoint)
        if "generate_responses" in entrypoint:
            return 1
        return 0

    monkeypatch.setattr(cli, "_run_entrypoint", fake_run_entrypoint)

    exit_code = cli.main(["run", "--lang", "go", "--model", "model"])

    assert exit_code == 1
    assert captured == [
        "experiments.evaluation.generation.generate_prompts:main",
        "experiments.evaluation.generation.generate_responses:main",
    ]


def test_run_rejects_partial_rag_tuning(monkeypatch, capsys) -> None:
    captured = _capture_dispatch(monkeypatch)

    exit_code = cli.main(
        [
            "run",
            "--lang",
            "go",
            "--model",
            "model",
            "--mode",
            "rag_bm25",
            "--context_size",
            "50",
        ]
    )

    assert exit_code == 2
    assert captured == []
    assert "must be provided together" in capsys.readouterr().err


def test_legacy_run_main_dispatches_to_evaluation(monkeypatch) -> None:
    captured = _capture_dispatch(monkeypatch)

    exit_code = cli.legacy_run_main(["--lang", "go", "--model", "my_model"])

    assert exit_code == 0
    assert captured[0]["entrypoint"] == "experiments.evaluation.run_evaluation:main"
    assert captured[0]["prog"] == "xrepotest-run"
    assert captured[0]["argv"] == ["--lang", "go", "--model", "my_model"]
