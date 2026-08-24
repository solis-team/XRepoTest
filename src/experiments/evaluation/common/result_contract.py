"""Typed result contract for generation and repair pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SUCCESS_STATUS = "success"
ERROR_STATUS = "error"
LEGACY_ERROR_PREFIXES = ("Error", "Exception", "[ERROR:")


@dataclass(frozen=True)
class GenerationResult:
    """Structured generation output."""

    status: str
    response: str
    error: str | None = None
    attempts: int = 1

    @property
    def is_success(self) -> bool:
        return self.status == SUCCESS_STATUS


def success_result(response: str, attempts: int = 1) -> GenerationResult:
    """Create a successful generation result."""
    # Ensure we don't treat empty responses as success
    if response is None or (isinstance(response, str) and not response.strip()):
        return error_result("Empty response from model", attempts=attempts)

    # If the response itself is a legacy error message, normalize it to ERROR_STATUS
    if isinstance(response, str) and response.startswith(LEGACY_ERROR_PREFIXES):
        return GenerationResult(
            status=ERROR_STATUS,
            response=response,
            error=response,
            attempts=attempts,
        )

    return GenerationResult(
        status=SUCCESS_STATUS,
        response=response,
        error=None,
        attempts=attempts,
    )


def error_result(message: str, attempts: int = 1) -> GenerationResult:
    """Create a failed generation result."""
    cleaned = (message or "").strip() or "Unknown generation error"
    return GenerationResult(
        status=ERROR_STATUS,
        response=f"Error: {cleaned}",
        error=cleaned,
        attempts=attempts,
    )


def infer_legacy_status(response: Any) -> str:
    """Infer status from legacy string responses."""
    if not isinstance(response, str):
        return SUCCESS_STATUS
    # Treat empty or whitespace-only as error
    if not response.strip():
        return ERROR_STATUS
    if response.startswith(LEGACY_ERROR_PREFIXES):
        return ERROR_STATUS
    return SUCCESS_STATUS


def record_status(record: Mapping[str, Any]) -> str:
    """Return normalized status from a result record."""
    status = record.get("status")
    if status in (SUCCESS_STATUS, ERROR_STATUS):
        return status
    return infer_legacy_status(record.get("response", ""))


def is_successful_record(record: Mapping[str, Any]) -> bool:
    """Check whether a record represents a successful generation."""
    if record_status(record) != SUCCESS_STATUS:
        return False
    
    # Extra safety check: response must not be empty or start with error prefix
    response = record.get("response")
    if not response or (isinstance(response, str) and not response.strip()):
        return False
    
    if isinstance(response, str) and response.startswith(LEGACY_ERROR_PREFIXES):
        return False
        
    return True


def to_response_record(
    *,
    task_id: Any,
    prompt: str,
    result: GenerationResult,
) -> dict[str, Any]:
    """Convert a typed result into a serialized JSONL record."""
    payload: dict[str, Any] = {
        "task_id": task_id,
        "prompt": prompt,
        "response": result.response,
        "status": result.status,
    }
    if result.error:
        payload["error"] = result.error
    return payload

