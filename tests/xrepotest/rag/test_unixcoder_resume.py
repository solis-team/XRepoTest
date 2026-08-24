import json

from xrepotest.rag.cache_manager import RAGCacheManager
from xrepotest.rag.retrieval import unixcoder_retriever as ur


def _sample(task_id, file_path="repo/src/a.py"):
    return {
        "task_id": task_id,
        "file_path": file_path,
        "function_name": "f",
        "function_component": {"start_line": 1, "end_line": 2},
        "focal_code": "def f():\n    pass",
    }


class _DummyRetriever:
    def __init__(self):
        self.preloaded = []

    def preload_repo_windows(self, windows_path):
        self.preloaded.append(windows_path)


def test_unixcoder_resume_reprocesses_rows_missing_unixcoder_field(monkeypatch, tmp_path):
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"

    samples = [_sample(1), _sample(2)]
    input_path.write_text("\n".join(json.dumps(s) for s in samples) + "\n", encoding="utf-8")

    manager = RAGCacheManager()
    # Existing row has the same task_id but no UniXcoder field yet (e.g., BM25-only output)
    manager.append_result(str(output_path), _sample(1))

    processed_ids = []

    def fake_retrieve_for_sample(sample, **kwargs):
        processed_ids.append(sample["task_id"])
        sample["retrieved_contexts_unixcoder"] = []
        return sample

    def normalize(sample):
        return sample

    monkeypatch.setattr(ur, "UniXcoderRetriever", _DummyRetriever)
    monkeypatch.setattr(ur, "retrieve_for_sample", fake_retrieve_for_sample)

    ur.process_file_unixcoder(
        input_path=str(input_path),
        output_path=str(output_path),
        windows_dir=str(tmp_path / "windows"),
        cache_manager=manager,
        normalize_task_id_fn=normalize,
    )

    assert processed_ids == [1, 2]
    out_ids = [json.loads(line)["task_id"] for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert set(out_ids) == {1, 2}


def test_unixcoder_resume_with_complete_output_does_no_processing(monkeypatch, tmp_path):
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"

    samples = [_sample(1), _sample(2)]
    input_path.write_text("\n".join(json.dumps(s) for s in samples) + "\n", encoding="utf-8")

    manager = RAGCacheManager()
    sample1 = _sample(1)
    sample1["retrieved_contexts_unixcoder"] = []
    sample2 = _sample(2)
    sample2["retrieved_contexts_unixcoder"] = []
    manager.append_result(str(output_path), sample1)
    manager.append_result(str(output_path), sample2)

    called = []

    def fake_retrieve_for_sample(sample, **kwargs):
        called.append(sample["task_id"])
        return sample

    def normalize(sample):
        return sample

    monkeypatch.setattr(ur, "UniXcoderRetriever", _DummyRetriever)
    monkeypatch.setattr(ur, "retrieve_for_sample", fake_retrieve_for_sample)

    ur.process_file_unixcoder(
        input_path=str(input_path),
        output_path=str(output_path),
        windows_dir=str(tmp_path / "windows"),
        cache_manager=manager,
        normalize_task_id_fn=normalize,
    )

    assert called == []
