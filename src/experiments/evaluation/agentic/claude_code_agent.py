"""Per-task headless Claude Code subprocess wrapper.

Adapted from crs-bug-finding-claude-code/agents/claude_code.py::run(), but
launched as a plain host subprocess (not inside a container) — Claude Code
simply inherits this devcontainer session's already-authenticated
environment, so no auth/env plumbing is needed here.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("agentic.claude_code_agent")

DEFAULT_ALLOWED_TOOLS = "Read,Grep,Bash,Edit"


@dataclass
class AgentRunResult:
    exit_reason: str  # "completed" | "timeout" | "crashed"
    returncode: Optional[int]
    wall_time_s: float
    cost_usd: Optional[float]
    num_turns: Optional[int]
    stdout_log_path: Path
    stderr_log_path: Path


def run_claude_code(
    *,
    cwd: Path,
    user_prompt: str,
    system_prompt: str,
    timeout_s: int,
    log_dir: Path,
    model: Optional[str] = None,
    allowed_tools: str = DEFAULT_ALLOWED_TOOLS,
) -> AgentRunResult:
    """Launch headless Claude Code for one task; block until it exits or the
    timeout is hit. Returns telemetry parsed from the stream-json log.

    `model` is omitted from the command by default (None) so the CLI uses
    its own ambient default model — this repo's mode/model folder names
    (e.g. "claude-sonnet-4-5") are proxy-specific aliases from config.py's
    Fireworks endpoint, not valid --model values for the natively
    authenticated `claude` CLI, and passing one that isn't recognized fails
    immediately with a model_not_found error (confirmed empirically)."""

    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = log_dir / "claude_stdout.ndjson"
    stderr_log = log_dir / "claude_stderr.log"

    cmd = [
        "claude",
        "-p",
        "--verbose",
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--effort", "low",
        "--allowedTools", allowed_tools,
        "--append-system-prompt", system_prompt,
    ]
    if model:
        cmd += ["--model", model]

    (log_dir / "prompt.txt").write_text(user_prompt, encoding="utf-8")
    (log_dir / "system_prompt.txt").write_text(system_prompt, encoding="utf-8")
    (log_dir / "cmd.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")

    start = time.monotonic()
    proc: Optional[subprocess.Popen] = None
    # Build subprocess environment with hardcoded API credentials so the
    # claude CLI can auth against the custom proxy without needing env
    # vars set in the calling shell. Values from settings.local.json.
    env = os.environ.copy()
    env.setdefault("ANTHROPIC_BASE_URL", "https://api.ai-box.vn")
    env.setdefault("ANTHROPIC_API_KEY", "sk-A6mszrZi4ZhK5G5ZsVS5ltS3PVAWGhU2frAl9HBk248FRRMs")
    env.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", "deepseek-v4-pro")
    env.setdefault("ANTHROPIC_DEFAULT_SONNET_MODEL", "deepseek-v4-pro")
    env.setdefault("ANTHROPIC_DEFAULT_HAIKU_MODEL", "deepseek-v4-flash")

    timed_out = False
    try:
        with open(stdout_log, "w", encoding="utf-8") as out_f, open(
            stderr_log, "w", encoding="utf-8"
        ) as err_f:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=out_f,
                stderr=err_f,
                text=True,
                cwd=str(cwd),
                start_new_session=True,
                env=env,
            )
            try:
                assert proc.stdin is not None
                proc.stdin.write(user_prompt)
                proc.stdin.close()
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                logger.warning("Claude Code timed out after %ds for %s", timeout_s, cwd)
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    time.sleep(2)
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
    except Exception as exc:
        logger.error("Error launching Claude Code for %s: %s", cwd, exc)
        wall_time = time.monotonic() - start
        return AgentRunResult(
            exit_reason="crashed",
            returncode=None,
            wall_time_s=wall_time,
            cost_usd=None,
            num_turns=None,
            stdout_log_path=stdout_log,
            stderr_log_path=stderr_log,
        )

    wall_time = time.monotonic() - start
    returncode = proc.returncode if proc is not None else None

    cost_usd, num_turns = _parse_terminal_result(stdout_log)

    if timed_out:
        exit_reason = "timeout"
        cost_usd = None
        num_turns = None
    elif returncode == 0:
        exit_reason = "completed"
    else:
        exit_reason = "crashed"

    return AgentRunResult(
        exit_reason=exit_reason,
        returncode=returncode,
        wall_time_s=wall_time,
        cost_usd=cost_usd,
        num_turns=num_turns,
        stdout_log_path=stdout_log,
        stderr_log_path=stderr_log,
    )


def _parse_terminal_result(stdout_log: Path) -> Tuple[Optional[float], Optional[int]]:
    """Parse the last well-formed `type: "result"` stream-json event for
    cost/turn telemetry.

    Field names (total_cost_usd/num_turns) are best-effort guesses based on
    general Claude Code SDK conventions, NOT verified against this specific
    pinned CLI version — per the plan, this must be confirmed empirically
    during the pilot smoke test. This function reads defensively and
    returns (None, None) rather than raising if the expected keys aren't
    present, so an unverified field name degrades to "unknown" telemetry
    instead of crashing the run.
    """
    if not stdout_log.exists():
        return None, None
    last_result: Optional[dict] = None
    try:
        with open(stdout_log, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "result":
                    last_result = event
    except OSError:
        return None, None

    if last_result is None:
        return None, None

    cost = last_result.get("total_cost_usd", last_result.get("cost_usd"))
    turns = last_result.get("num_turns", last_result.get("turn_count"))
    return cost, turns
