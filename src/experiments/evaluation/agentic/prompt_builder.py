"""CLAUDE.md + prompt construction for the agentic evaluation mode.

Structurally follows experiments.evaluation.repair.prompt_builder's
per-language-keyed design, extended with the repo-exploration/self-check
instructions an agentic (rather than blind single-turn) task needs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from experiments.evaluation.agentic.language_conventions import TaskPaths, get_convention

_SYSTEM_PROMPTS: Dict[str, str] = {
    "go": "You are an expert Go programmer specializing in writing robust, idiomatic test cases.",
    "rust": "You are an expert Rust programmer specializing in writing correct, memory-safe test cases.",
    "ruby": "You are an expert Ruby programmer specializing in writing thorough RSpec test cases.",
    "php": "You are an expert PHP programmer specializing in writing comprehensive PHPUnit test cases.",
    "julia": "You are an expert Julia programmer specializing in writing robust, idiomatic test cases using the Test standard library.",
}

_AGENTIC_ADDENDUM = (
    " You have full access to this repository's files and a shell (via Bash) — explore, "
    "compile, and run tests before finalizing your answer. Do not guess; verify."
)


class PromptBuilder:
    def __init__(self, language: str):
        self.language = language.strip().lower()
        if self.language not in _SYSTEM_PROMPTS:
            raise ValueError(f"Unsupported agentic-mode language: {language}")
        self.convention = get_convention(self.language)

    def get_system_prompt(self) -> str:
        return _SYSTEM_PROMPTS[self.language] + _AGENTIC_ADDENDUM

    def build_batch_claude_md(self, entries: List[Tuple[Dict[str, Any], TaskPaths]]) -> str:
        """One combined CLAUDE.md covering every target in a repo-batch run —
        the agent explores the repo once and writes tests for all of them in
        a single session, instead of paying repo-exploration cost per
        function. Targets sharing a directory/file (same package) list the
        same output path more than once by design; the agent is told to add
        to the shared file rather than treat each entry as isolated."""
        sections = []
        for i, (sample, paths) in enumerate(entries, start=1):
            function_name = sample["function_name"]
            output_contract = self.convention.output_contract_text(paths)
            self_check_cmd = self.convention.self_check_command_text(paths)
            sections.append(
                f"### Target {i}: `{function_name}`\n\n"
                f"- File: `{paths.focal_file}`\n\n"
                "Nothing about this function's signature, behavior, or dependencies is "
                "given here — read the file yourself before writing its test.\n\n"
                f"Output contract: {output_contract}\n\n"
                f"Your test must actually call `{function_name}` as a real function/method "
                "invocation — not just mention its name in a comment or string. The grader "
                "checks for a real call node in the test's syntax tree.\n\n"
                "Check your work for this target with:\n\n"
                "```\n" + self_check_cmd + "\n```\n"
            )

        scratch_root = entries[0][1].scratch_root
        return (
            "# Agentic Test Generation Task (repo batch)\n\n"
            f"You are generating unit tests for {len(entries)} separate functions in this "
            "repository, as part of a research benchmark. This is a sandboxed, disposable "
            f"copy of an open-source repository — nothing outside `{scratch_root}` will be "
            "affected by anything you do.\n\n"
            "Work through every target below. Some targets may share the same output file "
            "as another target (same package/directory) — if so, add your tests for both "
            "to that shared file rather than overwriting it.\n\n"
            "## Targets\n\n" + "\n".join(sections)
        )

    def build_batch_user_prompt(self, entries: List[Tuple[Dict[str, Any], TaskPaths]]) -> str:
        names = ", ".join(f"`{sample['function_name']}`" for sample, _ in entries)
        return (
            f"Write unit tests for the following {len(entries)} functions: {names}. "
            "Read CLAUDE.md in this directory for the full task list, environment, and "
            "output contract for each. Work through them one at a time, iterating until "
            "each compiles and passes, then move to the next. Stop once all targets are "
            "done or you run out of time."
        )
