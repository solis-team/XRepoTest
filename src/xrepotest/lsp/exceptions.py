"""Custom exceptions for the LSP enrichment pipeline."""


class LSPModuleError(Exception):
    """Base exception for xrepotest LSP module errors."""


class LSPConfigurationError(LSPModuleError):
    """Raised when language/server configuration is invalid or missing."""


class LSPExtractionError(LSPModuleError):
    """Raised when argument/type extraction fails for a function."""

    def __init__(self, function_name: str, reason: str):
        self.function_name = function_name
        self.reason = reason
        super().__init__(f"Failed to extract for function '{function_name}': {reason}")


class LSPEnrichmentError(LSPModuleError):
    """Raised when focal-method enrichment fails."""

    def __init__(self, function_name: str, reason: str):
        self.function_name = function_name
        self.reason = reason
        super().__init__(f"Failed to enrich function '{function_name}': {reason}")

