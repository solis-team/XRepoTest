"""Per-language test-file placement, self-check command, and result-capture
conventions for the agentic evaluation mode.

Single source of truth mirroring each language's real evaluator behavior
(``environments/<lang>/test_utils.py`` + ``command_utils.py``), so the
agent's local self-check predicts the real Docker eval outcome. Only the
four languages sharing the per-sample ``BaseEvaluator`` flow are covered
(Julia is excluded — its evaluator batches per-repository).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from experiments.evaluation.common.constants import LANGUAGE_DOCKER_IMAGES

AGENTIC_SUPPORTED_LANGUAGES: tuple[str, ...] = ("go", "rust", "ruby", "php", "julia")


@dataclass(frozen=True)
class TaskPaths:
    """Resolved filesystem locations for one task's scratch copy.

    ``rel_path`` is the focal file's path relative to the repo root (i.e.
    the dataset's ``file_path`` with the leading ``<repo_name>/`` segment
    stripped).
    """

    scratch_root: Path
    repo_name: str
    rel_path: str

    @property
    def repo_dir(self) -> Path:
        return self.scratch_root / self.repo_name

    @property
    def focal_file(self) -> Path:
        return self.repo_dir / self.rel_path

    @property
    def focal_dir(self) -> Path:
        return self.focal_file.parent

    def container_workdir(self, project_rel_dir: str) -> str:
        """Absolute path a nested `docker run -w` should use for this task,
        given a directory relative to the repo root (may be "")."""
        if project_rel_dir in ("", "."):
            return f"/workdir/{self.repo_name}"
        return f"/workdir/{self.repo_name}/{project_rel_dir}"


def _docker_run(image: str, scratch_root: Path, workdir: str, shell_cmd: str) -> str:
    return (
        f'docker run --rm -v "{scratch_root}":/workdir -w {workdir} '
        f'{image} sh -c "{shell_cmd}"'
    )


def _walk_up_for_marker(start_dir: Path, marker: str, floor: Path) -> Path:
    """Walk upward from start_dir looking for a directory containing
    `marker`, stopping at (and including) `floor`. Falls back to start_dir
    if not found, matching the real evaluators' own fallback behavior."""
    current = start_dir
    while True:
        if (current / marker).exists():
            return current
        if current == floor or current.parent == current:
            return start_dir
        current = current.parent


class LanguageConvention:
    language: str
    fence_tag: str

    def pre_clean(self, paths: TaskPaths) -> None:
        raise NotImplementedError

    def output_contract_text(self, paths: TaskPaths) -> str:
        raise NotImplementedError

    def self_check_command_text(self, paths: TaskPaths) -> str:
        raise NotImplementedError

    def locate_result(self, paths: TaskPaths, original_file_content: str) -> Optional[str]:
        raise NotImplementedError


class GoConvention(LanguageConvention):
    language = "go"
    fence_tag = "go"

    def pre_clean(self, paths: TaskPaths) -> None:
        for existing in paths.focal_dir.glob("*_test.go"):
            try:
                existing.unlink()
            except OSError:
                pass

    def _pkg_rel_dir(self, paths: TaskPaths) -> str:
        return os.path.dirname(paths.rel_path)

    def output_contract_text(self, paths: TaskPaths) -> str:
        return (
            f"Write your test to `{paths.focal_dir}/temp_test.go` — this exact "
            "filename, in the same directory (same package, for private-symbol "
            "access) as the focal file. The grading harness reads this file from "
            "disk, not your chat output. Any pre-existing `*_test.go` files in "
            "that directory have already been removed to match the grading "
            "environment — do not expect them and do not try to restore them. "
            "Test function names must start with `Test`."
        )

    def self_check_command_text(self, paths: TaskPaths) -> str:
        image = LANGUAGE_DOCKER_IMAGES["go"]
        workdir = paths.container_workdir(self._pkg_rel_dir(paths))
        # No "./..." here deliberately: the real evaluator runs `go test` in
        # the exact package dir only (non-recursive) — see command_utils.py's
        # check_compilation/check_test (cwd=package_dir, no "./..."). Testing
        # recursively would exercise sibling packages the focal function has
        # nothing to do with.
        return _docker_run(image, paths.scratch_root, workdir, "go test -c && go test -v .")

    def locate_result(self, paths: TaskPaths, original_file_content: str) -> Optional[str]:
        test_file = paths.focal_dir / "temp_test.go"
        if not test_file.exists():
            return None
        content = test_file.read_text(encoding="utf-8", errors="replace")
        return content if content.strip() else None


class RustConvention(LanguageConvention):
    language = "rust"
    fence_tag = "rust"

    def pre_clean(self, paths: TaskPaths) -> None:
        # Nothing to remove: the scratch copy is always a fresh copy of the
        # pristine repo_data checkout, so the focal file never already has a
        # tests_xrepotest module appended.
        return None

    def _project_rel_dir(self, paths: TaskPaths) -> str:
        probe = "/" + paths.rel_path
        if "/src/" in probe:
            before = probe.rsplit("/src/", 1)[0]
            return before.lstrip("/")
        return os.path.dirname(paths.rel_path)

    def output_contract_text(self, paths: TaskPaths) -> str:
        return (
            f"Append your test module directly to the end of the focal file "
            f"itself, `{paths.focal_file}` — do NOT create a separate file. "
            "Wrap it as `mod tests_xrepotest { ... }` (this exact module name "
            "is required — the grading harness filters on it). Do not repeat "
            "or redefine the focal function; only append the new test module "
            "after the existing file content."
        )

    def self_check_command_text(self, paths: TaskPaths) -> str:
        image = LANGUAGE_DOCKER_IMAGES["rust"]
        workdir = paths.container_workdir(self._project_rel_dir(paths))
        return _docker_run(image, paths.scratch_root, workdir, "cargo test tests_xrepotest")

    def locate_result(self, paths: TaskPaths, original_file_content: str) -> Optional[str]:
        if not paths.focal_file.exists():
            return None
        current = paths.focal_file.read_text(encoding="utf-8", errors="replace")
        if current.startswith(original_file_content):
            appended = current[len(original_file_content):].strip()
            return appended or None
        # Fallback: agent reformatted the file boundary — take from the first
        # `mod ...tests...` declaration onward. format_test_code() in the real
        # evaluator will still rename whatever module name is found.
        idx = current.find("mod ")
        while idx != -1:
            tail = current[idx:]
            if "test" in tail.split("{", 1)[0]:
                return tail.strip() or None
            idx = current.find("mod ", idx + 1)
        return None


class RubyConvention(LanguageConvention):
    language = "ruby"
    fence_tag = "ruby"

    def _project_root(self, paths: TaskPaths) -> Path:
        return _walk_up_for_marker(paths.focal_dir, "Gemfile", paths.repo_dir)

    def pre_clean(self, paths: TaskPaths) -> None:
        spec_dir = self._project_root(paths) / "spec"
        if not spec_dir.exists():
            return
        for existing in spec_dir.glob("temp_*_spec.rb"):
            try:
                existing.unlink()
            except OSError:
                pass

    def output_contract_text(self, paths: TaskPaths) -> str:
        project_root = self._project_root(paths)
        return (
            f"Write your test to `{project_root}/spec/temp_spec.rb` (RSpec "
            "convention) — this exact filename, creating the `spec/` directory "
            "if it doesn't already exist. The grading harness reads this file "
            "from disk, not your chat output. Any pre-existing `temp_*_spec.rb` "
            "files have already been removed to match the grading environment."
        )

    def self_check_command_text(self, paths: TaskPaths) -> str:
        project_root = self._project_root(paths)
        rel_project_dir = str(project_root.relative_to(paths.scratch_root).as_posix())
        workdir = f"/workdir/{rel_project_dir}" if rel_project_dir else f"/workdir/{paths.repo_name}"
        image = LANGUAGE_DOCKER_IMAGES["ruby"]
        cmd = "bundle exec rspec --format progress spec/temp_spec.rb || rspec spec/temp_spec.rb"
        return _docker_run(image, paths.scratch_root, workdir, cmd)

    def locate_result(self, paths: TaskPaths, original_file_content: str) -> Optional[str]:
        test_file = self._project_root(paths) / "spec" / "temp_spec.rb"
        if not test_file.exists():
            return None
        content = test_file.read_text(encoding="utf-8", errors="replace")
        return content if content.strip() else None


class PhpConvention(LanguageConvention):
    language = "php"
    fence_tag = "php"

    def __init__(self) -> None:
        # get_convention() returns a single shared instance of this class
        # (see _CONVENTIONS below), reused by every concurrently-running
        # repo batch. Keying snapshots by project root (unique per repo)
        # instead of one instance attribute keeps concurrent repos from
        # clobbering each other's mtime snapshot between pre_clean() and
        # the matching locate_result() call, which can be minutes apart.
        self._mtime_snapshots: dict[str, dict[str, float]] = {}

    def _project_root(self, paths: TaskPaths) -> Path:
        return _walk_up_for_marker(paths.focal_dir, "composer.json", paths.repo_dir)

    def pre_clean(self, paths: TaskPaths) -> None:
        # No fixed filename to remove (the agent's chosen class name decides
        # the filename) — snapshot mtimes instead, used by locate_result to
        # identify the file the agent actually created/modified this task.
        project_root = self._project_root(paths)
        tests_dir = project_root / "tests"
        snapshot: dict[str, float] = {}
        if tests_dir.exists():
            for f in tests_dir.glob("*.php"):
                try:
                    snapshot[str(f)] = f.stat().st_mtime
                except OSError:
                    continue
        self._mtime_snapshots[str(project_root)] = snapshot

    def output_contract_text(self, paths: TaskPaths) -> str:
        project_root = self._project_root(paths)
        return (
            f"Write your test to `{project_root}/tests/<ClassName>.php` (PHPUnit "
            "convention), where `<ClassName>` matches the `class` you declare in "
            "the test file — create the `tests/` directory if needed. Include "
            "`<?php` and `require_once __DIR__ . '/../vendor/autoload.php';`. "
            "The grading harness reads this file from disk, not your chat output."
        )

    def self_check_command_text(self, paths: TaskPaths) -> str:
        project_root = self._project_root(paths)
        rel_project_dir = str(project_root.relative_to(paths.scratch_root).as_posix())
        workdir = f"/workdir/{rel_project_dir}" if rel_project_dir else f"/workdir/{paths.repo_name}"
        image = LANGUAGE_DOCKER_IMAGES["php"]
        cmd = "php -l tests/*.php; php vendor/bin/phpunit tests/"
        return _docker_run(image, paths.scratch_root, workdir, cmd)

    def locate_result(self, paths: TaskPaths, original_file_content: str) -> Optional[str]:
        project_root = self._project_root(paths)
        tests_dir = project_root / "tests"
        if not tests_dir.exists():
            return None
        before = self._mtime_snapshots.get(str(project_root), {})
        candidates = []
        for f in tests_dir.glob("*.php"):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            prior = before.get(str(f))
            if prior is None or mtime > prior:
                candidates.append((mtime, f))
        if not candidates:
            return None
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        newest = candidates[0][1]
        content = newest.read_text(encoding="utf-8", errors="replace")
        return content if content.strip() else None


class JuliaConvention(LanguageConvention):
    language = "julia"
    fence_tag = "julia"

    def _project_root(self, paths: TaskPaths) -> Path:
        return _walk_up_for_marker(paths.focal_dir, "Project.toml", paths.repo_dir)

    def pre_clean(self, paths: TaskPaths) -> None:
        project_root = self._project_root(paths)
        test_dir = project_root / "test"
        if test_dir.exists():
            for f in test_dir.glob("temp_*xrepotest*.jl"):
                try:
                    f.unlink()
                except OSError:
                    pass

    def output_contract_text(self, paths: TaskPaths) -> str:
        project_root = self._project_root(paths)
        return (
            f"Write your test to `{project_root}/test/temp_xrepotest.jl` — this exact "
            "filename. Create the `test/` directory if it doesn't already exist. "
            "Include `using ModuleName` (check `Project.toml` for the module name) "
            "and `using Test`. Wrap your tests in an `@testset` block. "
            "The grading harness reads this file from disk, not your chat output. "
            "Any pre-existing `temp_*xrepotest*.jl` files have already been removed."
        )

    def self_check_command_text(self, paths: TaskPaths) -> str:
        project_root = self._project_root(paths)
        rel_project_dir = str(project_root.relative_to(paths.scratch_root).as_posix())
        workdir = (
            f"/workdir/{rel_project_dir}"
            if rel_project_dir
            else f"/workdir/{paths.repo_name}"
        )
        image = LANGUAGE_DOCKER_IMAGES["julia"]
        cmd = "julia --project=. -e 'include(\"test/temp_xrepotest.jl\")'"
        return _docker_run(image, paths.scratch_root, workdir, cmd)

    def locate_result(self, paths: TaskPaths, original_file_content: str) -> Optional[str]:
        test_file = self._project_root(paths) / "test" / "temp_xrepotest.jl"
        if not test_file.exists():
            return None
        content = test_file.read_text(encoding="utf-8", errors="replace")
        return content if content.strip() else None


_CONVENTIONS: dict[str, LanguageConvention] = {
    "go": GoConvention(),
    "rust": RustConvention(),
    "ruby": RubyConvention(),
    "php": PhpConvention(),
    "julia": JuliaConvention(),
}


def get_convention(language: str) -> LanguageConvention:
    key = language.strip().lower()
    if key not in _CONVENTIONS:
        raise ValueError(
            f"Unsupported agentic-mode language: {language}. "
            f"Supported: {', '.join(AGENTIC_SUPPORTED_LANGUAGES)}"
        )
    return _CONVENTIONS[key]
