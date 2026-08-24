"""Go LSP Client using gopls language server."""

from typing import List
from xrepotest.lsp.lsp_client.base_lsp import BaseLSPClient
from xrepotest.lsp.lsp_client.config import build_lsp_config


class GoLSPClient(BaseLSPClient):
    """LSP client for Go using gopls."""
    
    def __init__(self, project_path: str):
        """Initialize Go LSP client with gopls-specific configuration."""
        config = build_lsp_config("go")
        super().__init__(project_path, config)
    
    def get_server_command(self) -> List[str]:
        """Return the gopls command."""
        return ["gopls"]
    
    def get_language_id(self) -> str:
        """Return Go language identifier."""
        return "go"
