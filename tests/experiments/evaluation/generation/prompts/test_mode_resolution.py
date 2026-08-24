from argparse import Namespace

from experiments.evaluation.common.modes import DEFAULT_PROMPT_MODE, PROMPT_MODE_CHOICES as MODE_CHOICES


def _resolve_mode(mode: str | None) -> str:
    return mode if mode is not None else DEFAULT_PROMPT_MODE


def _options(**overrides: object) -> Namespace:
    base = {"mode": None}
    base.update(overrides)
    return Namespace(**base)


def test_resolve_mode_defaults_to_standard() -> None:
    opt = _options()
    assert _resolve_mode(opt.mode) == "standard"


def test_resolve_mode_prefers_explicit_mode() -> None:
    opt = _options(mode="file_context")
    assert _resolve_mode(opt.mode) == "file_context"


def test_resolve_mode_infers_rag_mode() -> None:
    opt = _options(mode="rag_dense")
    assert _resolve_mode(opt.mode) == "rag_dense"


def test_mode_choices_only_include_canonical_modes() -> None:
    assert MODE_CHOICES == (
        "standard",
        "lsp_context",
        "file_context",
        "rag_bm25",
        "rag_dense",
    )
