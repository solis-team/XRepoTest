"""Centralized configuration for xrepotest."""

from __future__ import annotations

from pathlib import Path

# API Configuration (used by CLI and core services)
# Base URL of the OpenAI-compatible endpoint. No provider default is baked in:
# the user MUST supply the endpoint (via the CLI's required `--api_base` flag,
# or by setting this constant to their provider). Keeping it empty ensures a
# request never silently targets a hardcoded host.
API_BASE_URL = ""

# Path to a plain-text file containing the API key (key only, no quotes/newlines).
# The secret itself lives outside the repo so this module can stay committed to git.
API_KEY_FILE = "/keys/api_key.key"


def _read_api_key_file(path: str = API_KEY_FILE) -> str:
    key_path = Path(path)
    if not key_path.is_file():
        return ""
    return key_path.read_text().strip()


API_KEY = _read_api_key_file()
OPENAI_API_KEY = API_KEY

# Runtime/Execution Defaults
RUN_RAG_CONTEXT_SIZE_CHOICES = (30, 50, 70)
RUN_DEFAULT_MAX_WORKERS = 20


__all__ = [
    "API_BASE_URL",
    "API_KEY",
    "API_KEY_FILE",
    "OPENAI_API_KEY",
    "RUN_DEFAULT_MAX_WORKERS",
    "RUN_RAG_CONTEXT_SIZE_CHOICES",
]
