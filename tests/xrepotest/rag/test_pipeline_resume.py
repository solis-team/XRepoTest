import json

from xrepotest.rag.cache_manager import RAGCacheManager
from xrepotest.rag.pipeline import RAGPipeline


def _sample(task_id, file_path="repo/src/a.py", fn_name="f", start=1, end=2):
    return {
        "task_id": task_id,
        "file_path": file_path,
        "function_name": fn_name,
        "function_component": {"start_line": start, "end_line": end},
        "focal_code": "def f():\n    pass",
    }


def test_load_existing_results_ignores_malformed_lines(tmp_path):
    path = tmp_path / "out.jsonl"
    path.write_text('{"task_id": 1}\nINVALID\n{"task_id": "2"}\n', encoding="utf-8")

    manager = RAGCacheManager()
    existing = manager.load_existing_results(str(path))

    assert set(existing.keys()) == {1, 2}


def test_filter_samples_skips_existing_ids(tmp_path):
    samples = [_sample(1), _sample(2), _sample(3)]
    path = tmp_path / "out.jsonl"
    RAGCacheManager().append_result(str(path), _sample(2))

    manager = RAGCacheManager()
    existing = manager.load_existing_results(str(path))
    remaining = manager.filter_samples(samples, existing)

    assert [s["task_id"] for s in remaining] == [1, 3]


def test_deduplicate_file_keeps_last_for_same_task_id(tmp_path):
    path = tmp_path / "out.jsonl"
    path.write_text(
        '\n'.join(
            [
                json.dumps({"task_id": 1, "value": "first"}),
                json.dumps({"task_id": 1, "value": "second"}),
                json.dumps({"task_id": 2, "value": "only"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manager = RAGCacheManager()
    manager.deduplicate_file(str(path))

    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    values_by_id = {line["task_id"]: line["value"] for line in lines}
    assert values_by_id[1] == "second"


def test_derive_stable_task_id_for_missing_task_id(tmp_path):
    pipeline = RAGPipeline(output_dir=str(tmp_path))
    first = _sample(None, file_path="repo/one.py", fn_name="f")
    second = _sample(None, file_path="repo/one.py", fn_name="f")

    pipeline._normalize_samples_task_ids([first, second])

    assert first["task_id"] == second["task_id"]


def test_pipeline_retrieval_uses_existing_output_for_bm25(monkeypatch, tmp_path):
    input_path = tmp_path / "input.jsonl"
    input_samples = [_sample(i, file_path="repo/one.py") for i in (1, 2)]
    input_path.write_text("\n".join(json.dumps(s) for s in input_samples) + "\n", encoding="utf-8")

    called = []

    def fake_retrieve_for_sample(sample, use_bm25=True, use_unixcoder=False):
        called.append(sample["task_id"])
        sample["retrieved_contexts_bm25"] = []
        return sample

    pipeline = RAGPipeline(output_dir=str(tmp_path))
    pipeline.retrieve_for_sample = fake_retrieve_for_sample
    manager = RAGCacheManager()

    base_output = tmp_path / "input_ws20_ss2_k10_enriched.jsonl"
    bm25_output = tmp_path / "input_ws20_ss2_k10_enriched_bm25.jsonl"
    manager.append_result(str(bm25_output), input_samples[0])

    pipeline.process_file(
        input_path=str(input_path),
        output_path=str(base_output),
        use_bm25=True,
        use_unixcoder=False,
    )

    assert called == [2]
    lines = [json.loads(line)["task_id"] for line in bm25_output.read_text().splitlines()]
    assert set(lines) == {1, 2}
