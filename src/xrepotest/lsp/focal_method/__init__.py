"""
Focal Method Context Enricher - Python Implementation of LSPRAG

This package implements the LSPRAG approach for extracting context from focal methods:
1. Token Extraction: Parse focal method body and extract all identifiers
2. Token Classification: Filter tokens into helpful vs unhelpful categories
3. Definition Retrieval: Query LSP for definitions of key tokens
4. Reference Retrieval: Query LSP for usage examples of key tokens

Based on the LSPRAG paper's approach to test generation context extraction.

Public API:
    FocalMethodEnricher: Main orchestrator class for focal method enrichment

Usage:
    from focal_method import FocalMethodEnricher
    
    enricher = FocalMethodEnricher(language='go', lsp_client=client)
    result = enricher.enrich_focal_method(function_data)
"""

from xrepotest.lsp.focal_method.enricher import FocalMethodEnricher

# Export the main public API
__all__ = ['FocalMethodEnricher']
