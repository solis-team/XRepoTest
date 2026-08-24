"""PHP LSP Client using Intelephense language server."""

from typing import List
from xrepotest.lsp.lsp_client.base_lsp import BaseLSPClient
from xrepotest.lsp.lsp_client.config import build_lsp_config


class PHPLSPClient(BaseLSPClient):
    """LSP client for PHP using Intelephense."""
    
    def __init__(self, project_path: str):
        """Initialize PHP LSP client with Intelephense-specific configuration."""
        config = build_lsp_config("php")
        super().__init__(project_path, config)
    
    def get_server_command(self) -> List[str]:
        """Return the Intelephense command."""
        return ["intelephense", "--stdio"]
    
    def get_language_id(self) -> str:
        """Return PHP language identifier."""
        return "php"
