"""Centralized configuration registry for language-specific LSP clients."""

from dataclasses import dataclass
import logging
from typing import Dict, Optional

from xrepotest.lsp.lsp_client.base_lsp import LSPConfig
from xrepotest.lsp.exceptions import LSPConfigurationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LanguageLSPDefaults:
    """Default LSP configuration values for a language."""

    startup_wait: float
    index_wait: float
    request_timeout: float
    extraction_timeout: float
    retry_count: int
    enable_retry: bool


LANGUAGE_LSP_DEFAULTS: Dict[str, LanguageLSPDefaults] = {
    "go": LanguageLSPDefaults(
        startup_wait=5.0,
        index_wait=180.0,
        request_timeout=10.0,
        extraction_timeout=30.0,
        retry_count=1,
        enable_retry=True,
    ),
    "rust": LanguageLSPDefaults(
        startup_wait=5.0,
        index_wait=180.0,
        request_timeout=10.0,
        extraction_timeout=30.0,
        retry_count=1,
        enable_retry=True,
    ),
    "ruby": LanguageLSPDefaults(
        startup_wait=5.0,
        index_wait=180.0,
        request_timeout=10.0,
        extraction_timeout=30.0,
        retry_count=1,
        enable_retry=True,
    ),
    "php": LanguageLSPDefaults(
        startup_wait=5.0,
        index_wait=180.0,
        request_timeout=10.0,
        extraction_timeout=30.0,
        retry_count=1,
        enable_retry=True,
    ),
    "julia": LanguageLSPDefaults(
        startup_wait=5.0,
        index_wait=180.0,
        request_timeout=10.0,
        extraction_timeout=30.0,
        retry_count=1,
        enable_retry=True,
    ),
}


def build_lsp_config(language: str, project_path: Optional[str] = None) -> LSPConfig:
    """Build a concrete ``LSPConfig`` from centralized language defaults."""
    normalized = language.lower()
    defaults = LANGUAGE_LSP_DEFAULTS.get(normalized)
    if defaults is None:
        raise LSPConfigurationError(
            f"No LSP configuration registered for language: {language}"
        )

    index_wait = defaults.index_wait

    return LSPConfig(
        startup_wait=defaults.startup_wait,
        index_wait=index_wait,
        request_timeout=defaults.request_timeout,
        extraction_timeout=defaults.extraction_timeout,
        retry_count=defaults.retry_count,
        enable_retry=defaults.enable_retry,
    )
