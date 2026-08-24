"""Julia LSP Client using Julia LanguageServer."""

import os
from typing import List, Dict, Any
from xrepotest.lsp.lsp_client.base_lsp import BaseLSPClient
from xrepotest.lsp.lsp_client.config import build_lsp_config


class JuliaLSPClient(BaseLSPClient):
    """LSP client for Julia with custom startup and longer timeouts."""
    
    def __init__(self, project_path: str):
        """Initialize Julia LSP client with Julia-specific configuration."""
        config = build_lsp_config("julia")
        super().__init__(project_path, config)
        # Use lsp_process for consistency with old code (will be mapped in property)
        self._process = None
    
    @property
    def lsp_process(self):
        """Compatibility property for old code that used lsp_process."""
        return self.process
    
    @lsp_process.setter
    def lsp_process(self, value):
        """Compatibility setter for old code."""
        self.process = value
    
    def get_server_command(self) -> List[str]:
        """Return the Julia language server command."""
        julia_script = """
using Pkg

try
    Pkg.instantiate()
catch err
    println(stderr, "Julia project instantiate failed; continuing with LanguageServer startup: ", err)
end

try
    using LanguageServer
catch
    using Pkg
    Pkg.add("LanguageServer")
    using LanguageServer
end
println(stderr, "Starting Julia Language Server...")

runserver()
"""
        return [
            "julia",
            "--startup-file=no",
            "--history-file=no",
            "--project=.",
            "-e",
            julia_script
        ]

    def get_language_id(self) -> str:
        """Return Julia language identifier."""
        return "julia"

    def get_init_options(self) -> Dict[str, Any]:
        """Return Julia-specific initialization options."""
        return {}

    def _initialize(self):
        """Initialize with longer timeout for Julia (600s due to slow precompilation)."""
        init_options = self.get_init_options()

        params = {
            "processId": os.getpid(),
            "rootPath": str(self.project_path),
            "rootUri": f"file://{self.project_path}",
            "capabilities": {
                "textDocument": {
                    "definition": {"dynamicRegistration": True},
                    "hover": {"dynamicRegistration": True}
                }
            }
        }

        if init_options:
            params["initializationOptions"] = init_options

        # Use 1200s timeout for Julia's slow initialization
        self._send_request("initialize", params, timeout=1200.0)
        self._send_notification("initialized", {})

    
    def start_lsp_server(self):
        """Alias method for compatibility with old code."""
        self.start()
    
    def open_document(self, file_path: str, content: str):
        """Open document with Julia-specific handling."""
        super().open_document(file_path, content)
