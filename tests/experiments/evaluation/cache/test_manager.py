import json
import threading

from experiments.evaluation.cache.manager import CacheManager


def test_filter_prompts_normalizes_task_id_types(tmp_path) -> None:
    output_file = tmp_path / "responses.jsonl"
    output_file.write_text(
        json.dumps({"task_id": "1", "response": "ok", "status": "success"}) + "\n",
        encoding="utf-8",
    )

    manager = CacheManager()
    existing_results = manager.load_existing_results(str(output_file))

    prompts = [{"task_id": 1, "prompt": "prompt"}]
    assert manager.filter_prompts(prompts, existing_results) == []


def test_append_result_writes_line(tmp_path) -> None:
    output_file = tmp_path / "responses.jsonl"
    manager = CacheManager()

    manager.append_result(str(output_file), {"task_id": 1, "response": "ok", "status": "success"})

    content = output_file.read_text(encoding="utf-8")
    lines = [l for l in content.splitlines() if l.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["task_id"] == 1
    assert parsed["response"] == "ok"


def test_append_result_thread_safe(tmp_path) -> None:
    output_file = str(tmp_path / "responses.jsonl")
    manager = CacheManager()
    num_threads = 10
    num_writes = 50

    def write_batch(start_id):
        for i in range(num_writes):
            manager.append_result(output_file, {
                "task_id": start_id * 1000 + i,
                "response": f"resp_{start_id}_{i}",
                "status": "success",
            })

    threads = []
    for t in range(num_threads):
        thread = threading.Thread(target=write_batch, args=(t,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    lines = []
    with open(output_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                lines.append(json.loads(line))

    assert len(lines) == num_threads * num_writes
    for line in lines:
        assert isinstance(line["task_id"], int)
        assert isinstance(json.loads(json.dumps(line)), dict)


def test_deduplicate_file_removes_duplicates(tmp_path) -> None:
    output_file = tmp_path / "responses.jsonl"
    output_file.write_text(
        json.dumps({"task_id": 1, "response": "old", "status": "success"}) + "\n"
        + json.dumps({"task_id": 1, "response": "new", "status": "success"}) + "\n",
        encoding="utf-8",
    )

    manager = CacheManager()
    manager.deduplicate_file(str(output_file))

    rows = [
        json.loads(line)
        for line in output_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    assert rows[0]["response"] == "new"


def test_deduplicate_file_preserves_unstable_task_ids(tmp_path) -> None:
    output_file = tmp_path / "responses.jsonl"
    output_file.write_text(
        json.dumps({"task_id": "unknown", "response": "first", "status": "success"}) + "\n"
        + json.dumps({"task_id": "unknown", "response": "second", "status": "success"}) + "\n",
        encoding="utf-8",
    )

    manager = CacheManager()
    manager.deduplicate_file(str(output_file))

    rows = [
        json.loads(line)
        for line in output_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 2
    assert [r["response"] for r in rows] == ["first", "second"]


def test_deduplicate_file_sorts_output(tmp_path) -> None:
    output_file = tmp_path / "responses.jsonl"
    output_file.write_text(
        json.dumps({"task_id": 3, "response": "c", "status": "success"}) + "\n"
        + json.dumps({"task_id": 1, "response": "a", "status": "success"}) + "\n"
        + json.dumps({"task_id": 2, "response": "b", "status": "success"}) + "\n",
        encoding="utf-8",
    )

    manager = CacheManager()
    manager.deduplicate_file(str(output_file))

    rows = [
        json.loads(line)
        for line in output_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [r["task_id"] for r in rows] == [1, 2, 3]


def test_deduplicate_file_skips_corrupted_lines(tmp_path) -> None:
    output_file = tmp_path / "responses.jsonl"
    output_file.write_text(
        json.dumps({"task_id": 1, "response": "ok", "status": "success"}) + "\n"
        + "this is not valid json\n"
        + json.dumps({"task_id": 2, "response": "also ok", "status": "success"}) + "\n",
        encoding="utf-8",
    )

    manager = CacheManager()
    manager.deduplicate_file(str(output_file))

    rows = [
        json.loads(line)
        for line in output_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 2
    assert {r["task_id"] for r in rows} == {1, 2}


def test_deduplicate_file_empty_file(tmp_path) -> None:
    output_file = tmp_path / "responses.jsonl"
    manager = CacheManager()
    manager.deduplicate_file(str(output_file))
    # Should not raise — no-op on missing file
