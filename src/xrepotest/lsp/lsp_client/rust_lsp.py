"""Rust LSP Client using rust-analyzer language server."""

from pathlib import Path
from typing import List, Dict, Any, Optional
from xrepotest.lsp.lsp_client.base_lsp import BaseLSPClient
from xrepotest.lsp.lsp_client.config import build_lsp_config


class RustLSPClient(BaseLSPClient):
    """LSP client for Rust using rust-analyzer with memory optimization."""
    
    @staticmethod
    def find_workspace_root(project_path: str) -> Optional[str]:
        """Find the Cargo workspace root by walking up the directory tree.
        
        Args:
            project_path: Path to a crate directory
            
        Returns:
            Path to workspace root if found, None otherwise
        """
        current = Path(project_path).resolve()
        
        # Walk up the directory tree
        for parent in [current] + list(current.parents):
            cargo_toml = parent / "Cargo.toml"
            if cargo_toml.exists():
                try:
                    content = cargo_toml.read_text()
                    # Check if this is a workspace manifest
                    if "[workspace]" in content:
                        return str(parent)
                except Exception:
                    pass
        
        return None
    
    def __init__(self, project_path: str):
        """Initialize Rust LSP client with rust-analyzer-specific configuration.
        
        Automatically detects Cargo workspaces and uses the workspace root for LSP initialization.
        This is critical for resolving cross-crate dependencies in multi-crate projects.
        """
        # Detect if this is part of a Cargo workspace
        workspace_root = self.find_workspace_root(project_path)
        if workspace_root and workspace_root != project_path:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Detected Cargo workspace root: {workspace_root}")
            logger.info(f"Using workspace root instead of crate path: {project_path}")
            project_path = workspace_root
        
        config = build_lsp_config("rust", project_path=project_path)
        super().__init__(project_path, config)
    
    def get_server_command(self) -> List[str]:
        """Return the rust-analyzer command."""
        return ["rust-analyzer"]
    
    def get_language_id(self) -> str:
        """Return Rust language identifier."""
        return "rust"
    
    def get_init_options(self) -> Dict[str, Any]:
        """Return rust-analyzer initialization options with memory optimization."""
        return {
            "checkOnSave": {
                "command": "clippy"
            },
            "cargo": {
                "allFeatures": False,
                "loadOutDirsFromCheck": True
            },
            "procMacro": {
                "enable": True
            },
            "diagnostics": {
                "enable": True,
                "disabled": ["unresolved-proc-macro"]
            },
            "assist": {
                "importGranularity": "module",
                "importPrefix": "by_self"
            },
            "inlayHints": {
                "enable": False
            }
        }
    
    def close(self):
        """Close the server."""
        super().close()
