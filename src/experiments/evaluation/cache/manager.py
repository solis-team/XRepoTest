import json
import os
import threading

from experiments.evaluation.common.task_ids import normalize_task_id, task_id_sort_key
from experiments.evaluation.common.result_contract import ERROR_STATUS, is_successful_record, record_status


class CacheManager:
    """
    Manages reading and writing of results to maintain cache/state.
    """
    def __init__(self):
        self.lock = threading.Lock()

    @staticmethod
    def _is_dedupe_candidate(task_id):
        """Return whether a task_id is stable enough for dedupe/index lookups."""
        if task_id is None:
            return False
        if isinstance(task_id, str) and task_id in {"", "unknown"}:
            return False
        return True

    def load_existing_results(self, file_path):
        """
        Load existing results from a JSONL file.

        Args:
            file_path (str): Path to the output JSONL file.

        Returns:
            dict: Dictionary mapping task_id to result data.
        """
        existing_responses = {}
        if os.path.exists(file_path):
            print(f"Found existing responses file: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            task_id = normalize_task_id(data.get('task_id'))
                            data["task_id"] = task_id
                            if is_successful_record(data) and self._is_dedupe_candidate(task_id):
                                existing_responses[task_id] = data
                        except json.JSONDecodeError:
                            continue
            print(f"Loaded {len(existing_responses)} existing successful responses")
        return existing_responses

    def filter_prompts(self, prompts, existing_results):
        """
        Filter out prompts that have already been successfully processed.

        Args:
            prompts (list): List of prompt dictionaries.
            existing_results (dict): Dictionary of existing results.

        Returns:
            list: List of prompts that still need processing.
        """
        prompts_to_process = [
            p
            for p in prompts
            if normalize_task_id(p.get("task_id")) not in existing_results
        ]

        if len(prompts_to_process) == 0:
            print(f"All {len(prompts)} prompts already have responses. Skipping.")
        else:
            print(f"Processing {len(prompts_to_process)} prompts ({len(existing_results)} already completed)...")

        return prompts_to_process

    def append_result(self, file_path, result):
        """
        Append a single result record to a JSONL file under the instance lock.

        Flushes to the OS buffer so data survives process death. Does NOT
        fsync — the marginal durability gain is not worth the throughput cost
        when writes are serialized behind the lock.
        """
        with self.lock:
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result) + '\n')
                f.flush()

    def deduplicate_file(self, file_path):
        """
        Read the JSONL file, deduplicate by normalized task_id (last
        occurrence wins), sort, and rewrite atomically via temp+rename.

        Records with unstable task_ids (None, empty, "unknown") are
        preserved as-is without deduplication. Corrupted lines are
        silently skipped.

        Holds the instance lock for the full read-rewrite cycle to
        prevent a concurrent append from being lost.
        """
        with self.lock:
            records = []
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue

            results_by_task_id = {}
            passthrough_results = []
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

            temp_file = file_path + '.tmp'
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    for record in all_results:
                        f.write(json.dumps(record) + '\n')
                os.replace(temp_file, file_path)
            except Exception:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                raise
