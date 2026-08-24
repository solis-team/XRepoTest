"""Ruby LSP Client using Solargraph language server."""

from typing import List
from xrepotest.lsp.lsp_client.base_lsp import BaseLSPClient
from xrepotest.lsp.lsp_client.config import build_lsp_config


class RubyLSPClient(BaseLSPClient):
    """LSP client for Ruby using Solargraph."""
    
    def __init__(self, project_path: str):
        """Initialize Ruby LSP client with Solargraph-specific configuration."""
        config = build_lsp_config("ruby")
        super().__init__(project_path, config)
    
    def get_server_command(self) -> List[str]:
        """Return the Solargraph command."""
        return ["solargraph", "stdio"]
    
    def get_language_id(self) -> str:
        """Return Ruby language identifier."""
        return "ruby"
