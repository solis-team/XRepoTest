import json
import os
import threading
from typing import Any

from experiments.evaluation.common.task_ids import normalize_task_id, task_id_sort_key


class RAGCacheManager:
    def __init__(self):
        self.lock = threading.Lock()

    @staticmethod
    def _is_dedupe_candidate(task_id: Any) -> bool:
        if task_id is None:
            return False
        if isinstance(task_id, str) and task_id in {"", "unknown"}:
            return False
        return True

    def load_existing_results(self, file_path: str) -> dict[Any, dict[str, Any]]:
        existing_results: dict[Any, dict[str, Any]] = {}
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    task_id = normalize_task_id(data.get("task_id"))
                    data["task_id"] = task_id
                    if self._is_dedupe_candidate(task_id):
                        existing_results[task_id] = data
        return existing_results

    def filter_samples(self, samples: list[dict[str, Any]], existing_results: dict[Any, dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            sample
            for sample in samples
            if normalize_task_id(sample.get("task_id")) not in existing_results
        ]

    def append_result(self, file_path: str, result: dict[str, Any]) -> None:
        with self.lock:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                f.flush()

    def deduplicate_file(self, file_path: str) -> None:
        with self.lock:
            records: list[dict[str, Any]] = []
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

            results_by_task_id: dict[Any, dict[str, Any]] = {}
            passthrough_results: list[dict[str, Any]] = []
            for record in records:
                task_id = normalize_task_id(record.get("task_id"))
                record["task_id"] = task_id
                if self._is_dedupe_candidate(task_id):
                    results_by_task_id[task_id] = record
                else:
                    passthrough_results.append(record)

            all_results = sorted(
                [*results_by_task_id.values(), *passthrough_results],
                key=lambda r: task_id_sort_key(r.get("task_id")),
            )

            temp_file = file_path + ".tmp"
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    for record in all_results:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                os.replace(temp_file, file_path)
            except Exception:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                raise
