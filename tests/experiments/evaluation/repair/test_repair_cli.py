import json
from argparse import Namespace

import experiments.evaluation.cache.manager as cache_manager_module
import experiments.evaluation.repair.repair_cli as repair_cli_module
from experiments.evaluation.common.result_contract import success_result


class StubOpenAIClient:
    def __init__(self, **kwargs):
        pass

    def generate_result(self, prompt, system_prompt, model, temperature):
        return success_result("repaired test body")


def _write_input_results(path, n):
    with open(path, "w", encoding="utf-8") as f:
        for i in range(n):
            sample = {
                "task_id": i,
                "test": ["func TestFoo(t *testing.T) {}"],
                "logs": ["assertion failed"],
                "checks": [{"compilation": False, "tests": False}],
            }
            f.write(json.dumps(sample) + "\n")


def _make_args(tmp_path, input_path, output_dir):
    return Namespace(
        input_results=str(input_path),
        output_dir=str(output_dir),
        language="go",
        attempt=1,
        max_attempts=3,
        concurrency=4,
        repair_model="stub-model",
        repair_provider="openai",
        base_url=None,
        api_key=None,
        temperature=0.0,
        delay=0.0,
        max_retries=3,
        retry_delay=5.0,
    )


def test_run_repair_appends_exactly_once_per_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(repair_cli_module, "OpenAIClient", StubOpenAIClient)

    append_calls = []
    original_append = cache_manager_module.CacheManager.append_result

    def spy_append(self, file_path, result):
        append_calls.append(result.get("task_id"))
        return original_append(self, file_path, result)

    monkeypatch.setattr(cache_manager_module.CacheManager, "append_result", spy_append)

    input_path = tmp_path / "detailed_results.jsonl"
    output_dir = tmp_path / "repair"
    num_samples = 15
    _write_input_results(input_path, num_samples)

    args = _make_args(tmp_path, input_path, output_dir)
    result_code = repair_cli_module.run_repair(args)

    assert result_code == 0
    # One append per sample via on_result — the redundant post-loop append
    # (which double-wrote every record) must not exist anymore.
    assert len(append_calls) == num_samples

    attempt_output = repair_cli_module.get_attempt_output_path(str(output_dir), 1)
    with open(attempt_output, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    task_ids = [line["task_id"] for line in lines]
    assert len(task_ids) == num_samples
    assert len(task_ids) == len(set(task_ids))
