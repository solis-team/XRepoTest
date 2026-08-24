"""AgenticEngine — orchestrates the agentic evaluation mode.

Per repo: copy the repo into a scratch dir once, pre-clean per the language
convention for every selected sample in it, write one combined CLAUDE.md,
invoke a single headless Claude Code session covering all of that repo's
samples (cheaper than one session per function, since repo-exploration
cost is paid once), read back each sample's result, package each into the
same prompts_responses.jsonl shape every other mode produces, and append
incrementally (resumable, same idiom as generate_responses.py /
repair/engine.py).
"""

from __future__ import annotations

import concurrent.futures
import logging
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from experiments.evaluation.agentic.claude_code_agent import AgentRunResult, run_claude_code
from experiments.evaluation.agentic.language_conventions import TaskPaths, get_convention
from experiments.evaluation.agentic.prompt_builder import PromptBuilder
from experiments.evaluation.cache.manager import CacheManager
from experiments.evaluation.common.result_contract import (
    error_result,
    success_result,
    to_response_record,
)
from experiments.evaluation.common.task_ids import normalize_task_id
from xrepotest.paths import get_evaluation_data_dir, get_repo_data_dir

logger = logging.getLogger("agentic.engine")

DEFAULT_MAX_WORKERS = 4
DEFAULT_TIMEOUT_S = 1800


class AgenticEngine:
    def __init__(
        self,
        language: str,
        model: Optional[str] = None,
        max_workers: int = DEFAULT_MAX_WORKERS,
        task_timeout_s: int = DEFAULT_TIMEOUT_S,
        scratch_base_dir: Optional[Path] = None,
        meta_output_path: Optional[Path] = None,
    ):
        self.language = language.strip().lower()
        self.model = model
        self.max_workers = max_workers
        self.timeout_s = task_timeout_s
        self.convention = get_convention(self.language)
        self.prompt_builder = PromptBuilder(self.language)
        self.cache_manager = CacheManager()

        self.scratch_base_dir = scratch_base_dir or (
            get_evaluation_data_dir() / "agentic_scratch" / self.language
        )
        self.meta_output_path = meta_output_path

    def run(
        self,
        samples: List[Dict[str, Any]],
        output_path: Path,
        on_result: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[Dict[str, Any]]:
        print(f"\n{'=' * 70}")
        print(f"Agentic Evaluation for {self.language.upper()} — model={self.model}")
        print(f"Samples: {len(samples)}  Concurrency: {self.max_workers}")
        print(f"{'=' * 70}\n")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.cache_manager.load_existing_results(str(output_path))

        pending = [s for s in samples if normalize_task_id(s.get("task_id")) not in existing]
        if not pending:
            print("All samples already have successful responses. Skipping.")
            return []

        print(
            f"Processing {len(pending)}/{len(samples)} samples "
            f"({len(existing)} already completed)..."
        )

        # One unit of work is a whole repo: all its pending samples share one
        # claude session and one scratch copy (the agent pays repo-exploration
        # cost once instead of once per function). Each unit returns a list of
        # response records, one per sample.
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for s in pending:
            repo_name = s["file_path"].split("/", 1)[0]
            groups[repo_name].append(s)
        units: List[Tuple[str, List[Dict[str, Any]]]] = list(groups.items())
        print(
            f"Grouped into {len(units)} repo batch(es): "
            + ", ".join(f"{repo}({len(g)})" for repo, g in units)
        )

        results: List[Dict[str, Any]] = []
        total_pending = len(pending)
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_unit = {
                executor.submit(self._run_repo_batch, repo_name, group_samples): (
                    repo_name,
                    group_samples,
                )
                for repo_name, group_samples in units
            }
            completed = 0
            for future in concurrent.futures.as_completed(future_to_unit):
                repo_name, group_samples = future_to_unit[future]
                try:
                    records = future.result()
                except Exception as exc:
                    logger.exception("Repo batch %s raised an exception", repo_name)
                    records = [
                        to_response_record(
                            task_id=normalize_task_id(s.get("task_id")),
                            prompt="",
                            result=error_result(f"Exception: {exc}"),
                        )
                        for s in group_samples
                    ]
                for record in records:
                    results.append(record)
                    self.cache_manager.append_result(str(output_path), record)
                    if on_result is not None:
                        on_result(record)
                    completed += 1
                    if completed % 5 == 0 or completed == total_pending:
                        print(f"Progress: {completed}/{total_pending} tasks processed")

        self.cache_manager.deduplicate_file(str(output_path))
        print(f"\nCompleted agentic pass. Processed {len(results)} tasks.")
        return results

    def _run_repo_batch(
        self, repo_name: str, samples: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """One claude session covering every sample in this repo — the agent
        pays repo-exploration cost once instead of once per function. Budget
        and timeout scale with the number of samples in the batch (an upper
        bound; real spend is expected to be sub-linear since context/session
        setup is shared). Each sample still gets its own response record so
        the output shape and downstream pipeline are unaffected."""
        scratch_root = self.scratch_base_dir / f"repo_{repo_name}"
        source_repo_dir = get_repo_data_dir() / self.language / repo_name

        try:
            self._prepare_scratch(source_repo_dir, scratch_root, repo_name)

            entries: List[Tuple[Dict[str, Any], TaskPaths]] = []
            for sample in samples:
                file_path = sample["file_path"]
                _, sep, rel_path = file_path.partition("/")
                if not sep:
                    raise ValueError(f"Unexpected file_path with no repo segment: {file_path}")
                paths = TaskPaths(scratch_root=scratch_root, repo_name=repo_name, rel_path=rel_path)
                self.convention.pre_clean(paths)
                entries.append((sample, paths))

            claude_md = self.prompt_builder.build_batch_claude_md(entries)
            (scratch_root / repo_name / "CLAUDE.md").write_text(claude_md, encoding="utf-8")

            user_prompt = self.prompt_builder.build_batch_user_prompt(entries)
            system_prompt = self.prompt_builder.get_system_prompt()

            log_dir = self.scratch_base_dir / "_agent_logs" / f"repo_{repo_name}"
            batch_task_ids = [normalize_task_id(s.get("task_id")) for s in samples]
            agent_result = run_claude_code(
                cwd=scratch_root / repo_name,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                model=self.model,
                timeout_s=self.timeout_s,
                log_dir=log_dir,
            )

            records: List[Dict[str, Any]] = []
            for sample, paths in entries:
                task_id = normalize_task_id(sample.get("task_id"))
                self._write_meta(task_id, agent_result, batch_task_ids=batch_task_ids)

                original_file_content = sample.get("file_content", "")
                captured = self.convention.locate_result(paths, original_file_content)

                if captured is None:
                    reason_map = {
                        "timeout": "timeout: no test file produced",
                    }
                    reason = reason_map.get(
                        agent_result.exit_reason,
                        f"claude process exited (reason={agent_result.exit_reason}, "
                        f"returncode={agent_result.returncode}): no test file produced",
                    )
                    records.append(
                        to_response_record(
                            task_id=task_id, prompt=user_prompt, result=error_result(reason)
                        )
                    )
                else:
                    fenced = f"```{self.convention.fence_tag}\n{captured}\n```"
                    records.append(
                        to_response_record(
                            task_id=task_id, prompt=user_prompt, result=success_result(fenced)
                        )
                    )
            return records
        finally:
            shutil.rmtree(scratch_root, ignore_errors=True)

    def _prepare_scratch(self, source_repo_dir: Path, scratch_root: Path, repo_name: str) -> None:
        if scratch_root.exists():
            shutil.rmtree(scratch_root, ignore_errors=True)
        scratch_root.mkdir(parents=True, exist_ok=True)
        if not source_repo_dir.exists():
            raise FileNotFoundError(f"repo_data checkout not found: {source_repo_dir}")
        shutil.copytree(source_repo_dir, scratch_root / repo_name)

    def _write_meta(
        self,
        task_id: Any,
        agent_result: AgentRunResult,
        batch_task_ids: Optional[List[Any]] = None,
    ) -> None:
        if self.meta_output_path is None:
            return
        record = {
            "task_id": task_id,
            "wall_time_s": round(agent_result.wall_time_s, 2),
            "cost_usd": agent_result.cost_usd,
            "num_turns": agent_result.num_turns,
            "exit_reason": agent_result.exit_reason,
            "claude_returncode": agent_result.returncode,
        }
        if batch_task_ids is not None:
            record["batch_task_ids"] = batch_task_ids
        self.meta_output_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_manager.append_result(str(self.meta_output_path), record)
