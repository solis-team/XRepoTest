from experiments.evaluation.common.result_contract import ERROR_STATUS, success_result
from experiments.evaluation.repair.engine import RepairEngine


class StubLLMClient:
    def __init__(self):
        self.calls = 0

    def generate_result(self, prompt, system_prompt, model, temperature):
        self.calls += 1
        return success_result(f"repaired test body #{self.calls}")


def _make_sample(task_id):
    return {
        "task_id": task_id,
        "test": ["func TestFoo(t *testing.T) {}"],
        "logs": ["assertion failed"],
        "checks": [{"compilation": False, "tests": False}],
    }


def _make_engine(max_workers=4):
    return RepairEngine(
        language="go",
        llm_client=StubLLMClient(),
        model="stub-model",
        temperature=0.0,
        max_workers=max_workers,
    )


def test_repair_single_pass_calls_on_result_per_sample():
    engine = _make_engine()
    samples = [_make_sample(i) for i in range(12)]

    seen_task_ids = []
    repaired_dataset, metrics_summary = engine.repair_single_pass(
        samples, attempt_number=1, on_result=lambda r: seen_task_ids.append(r["task_id"])
    )

    assert len(seen_task_ids) == len(samples)
    assert set(seen_task_ids) == {s["task_id"] for s in samples}
    assert metrics_summary["total_samples"] == len(samples)
    assert {r["task_id"] for r in repaired_dataset} == set(seen_task_ids)


def test_repair_single_pass_persists_error_record_on_unexpected_exception(monkeypatch):
    engine = _make_engine()
    samples = [_make_sample(0), _make_sample(1), _make_sample(2)]

    original_repair_sample = engine._repair_sample

    def flaky_repair_sample(sample, task_id):
        if task_id == 1:
            raise RuntimeError("boom")
        return original_repair_sample(sample, task_id)

    monkeypatch.setattr(engine, "_repair_sample", flaky_repair_sample)

    on_result_records = []
    repaired_dataset, metrics_summary = engine.repair_single_pass(
        samples, attempt_number=1, on_result=on_result_records.append
    )

    # No sample is silently dropped, even the one whose worker raised.
    assert len(repaired_dataset) == 3
    assert len(on_result_records) == 3
    assert metrics_summary["total_samples"] == 3

    failed = next(r for r in on_result_records if r["task_id"] == 1)
    assert failed["status"] == ERROR_STATUS
    assert "Exception: boom" in failed["response"]
    assert failed in repaired_dataset
