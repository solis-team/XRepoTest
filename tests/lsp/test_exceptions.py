import pytest

from xrepotest.lsp.exceptions import (
    LSPEnrichmentError,
    LSPExtractionError,
    LSPModuleError,
)


@pytest.mark.parametrize(
    ("exception_cls", "expected_message"),
    [
        (
            LSPExtractionError,
            "Failed to extract for function 'my_func': parser failed",
        ),
        (
            LSPEnrichmentError,
            "Failed to enrich function 'my_func': dependency missing",
        ),
    ],
)
def test_lsp_function_errors_store_fields_and_message(exception_cls, expected_message):
    reason = "parser failed" if exception_cls is LSPExtractionError else "dependency missing"
    err = exception_cls(function_name="my_func", reason=reason)

    assert err.function_name == "my_func"
    assert err.reason == reason
    assert str(err) == expected_message


@pytest.mark.parametrize("exception_cls", [LSPExtractionError, LSPEnrichmentError])
def test_lsp_function_errors_subclass_module_error(exception_cls):
    assert issubclass(exception_cls, LSPModuleError)
