"""
Base LSP Client class with common functionality for all language servers.

This module provides an abstract base class that implements common LSP protocol
communication patterns, reducing code duplication across language-specific clients.
"""

import json
import subprocess
import os
import threading
import queue
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class LSPConfig:
    """Configuration for LSP client behavior"""
    startup_wait: float = 2.0  # Initial wait after starting server
    index_wait: float = 10.0  # Wait for indexing after initialization
    request_timeout: float = 10.0  # Default timeout for requests
    extraction_timeout: float = 30.0  # Timeout per function during extraction
    retry_count: int = 2  # Number of retries for failed requests
    enable_retry: bool = True  # Enable automatic retry logic
    poll_interval: float = 0.5  # Polling interval for response queue


class LSPError(Exception):
    """Base exception for LSP errors"""
    pass


class LSPTimeoutError(LSPError, TimeoutError):
    """Request timed out"""
    pass


class LSPProcessError(LSPError, RuntimeError):
    """LSP server process error"""
    pass


class LSPResponseError(LSPError, ValueError):
    """Invalid or unexpected LSP response"""
    pass


class BaseLSPClient(ABC):
    """
    Abstract base class for LSP clients.
    
    Subclasses must implement:
    - get_server_command(): Return the command to start the LSP server
    - get_language_id(): Return the language identifier for textDocument/didOpen
    - get_init_options(): Return initialization options (optional)
    """
    
    def __init__(self, project_path: str, config: Optional[LSPConfig] = None):
        """
        Initialize the LSP client.
        
        Args:
            project_path: Path to the project root
            config: LSP configuration (uses defaults if not provided)
        """
        self.project_path = Path(project_path)
        self.config = config or LSPConfig()
        self.process = None
        self.request_id = 0
        self.response_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.reader_thread = None
        self.stderr_thread = None
    
    @abstractmethod
    def get_server_command(self) -> List[str]:
        """Return the command to start the LSP server."""
        pass
    
    @abstractmethod
    def get_language_id(self) -> str:
        """Return the language identifier (e.g., 'python', 'go', 'rust')."""
        pass
    
    def get_init_options(self) -> Dict[str, Any]:
        """
        Return initialization options for the LSP server.
        Override this in subclasses to provide language-specific options.
        """
        return {}
    
    def get_index_wait_time(self) -> float:
        """
        Return the wait time for indexing after initialization.
        Override in subclasses if language needs different timing.
        """
        return self.config.index_wait
    
    def start(self):
        """Start the LSP server process and initialize communication."""
        if self.process is not None:
            logger.warning("LSP server already started")
            return
        
        # Start the server process
        server_command = self.get_server_command()
        logger.info(f"Starting LSP server: {' '.join(server_command)}")
        
        self.process = subprocess.Popen(
            server_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.project_path,
            bufsize=0
        )
        
        # Start reader threads
        self.reader_thread = threading.Thread(target=self._read_responses, daemon=True)
        self.reader_thread.start()
        
        self.stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self.stderr_thread.start()
        
        # Wait for server to start
        time.sleep(self.config.startup_wait)
        
        # Initialize the server
        self._initialize()
        
        # Wait for indexing
        index_wait = self.get_index_wait_time()
        logger.debug(f"Waiting {index_wait}s for indexing...")
        time.sleep(index_wait)
        
        logger.info("LSP server ready")
    
    def _read_responses(self):
        """Read responses from the language server stdout."""
        while not self.stop_event.is_set() and self.process and self.process.poll() is None:
            try:
                header = self.process.stdout.readline()
                if not header:
                    break
                if not header.startswith(b"Content-Length:"):
                    continue
                    
                length = int(header.strip().split(b": ")[1])
                self.process.stdout.readline()  # Skip empty line
                content = self.process.stdout.read(length)
                
                message = json.loads(content.decode())
                self.response_queue.put(message)
                
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping malformed JSON: {e}")
                continue
            except Exception as e:
                if not self.stop_event.is_set():
                    logger.error(f"Response read error: {e}")
                break
    
    def _read_stderr(self):
        """Read stderr output from the language server."""
        while not self.stop_event.is_set() and self.process and self.process.poll() is None:
            try:
                line = self.process.stderr.readline()
                if line:
                    logger.debug(f"[stderr] {line.decode().strip()}")
            except Exception as e:
                if not self.stop_event.is_set():
                    logger.error(f"Stderr read error: {e}")
                break
    
    def _send_request(self, method: str, params: Dict, timeout: Optional[float] = None, retries: Optional[int] = None) -> Dict:
        """
        Send a request to the language server and wait for response.
        
        Args:
            method: LSP method name
            params: Request parameters
            timeout: Timeout in seconds (uses config default if not specified)
            retries: Number of retries (uses config default if not specified)
            
        Returns:
            Response dictionary
            
        Raises:
            LSPProcessError: If server process is not running
            LSPTimeoutError: If request times out
        """
        # Check if subprocess is running
        if self.process is None or self.process.poll() is not None:
            raise LSPProcessError(
                f"LSP server process is not running (exit code: {self.process.poll() if self.process else 'None'})"
            )
        
        timeout = timeout or self.config.request_timeout
        retries = retries if retries is not None else (self.config.retry_count if self.config.enable_retry else 0)
        
        for attempt in range(retries + 1):
            try:
                return self._do_send_request(method, params, timeout)
            except LSPTimeoutError as e:
                if attempt < retries:
                    logger.warning(f"Retry {attempt + 1}/{retries} for {method} after timeout")
                    time.sleep(1)  # Brief wait before retry
                else:
                    raise e
        
        # Should never reach here
        raise LSPTimeoutError(f"Request {method} failed after {retries + 1} attempts")
    
    def _do_send_request(self, method: str, params: Dict, timeout: float) -> Dict:
        """Internal method to send a single request."""
        self.request_id += 1
        expected_id = self.request_id
        
        message = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params
        }
        
        body = json.dumps(message)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        
        self.process.stdin.write((header + body).encode())
        self.process.stdin.flush()
        
        logger.debug(f"Sent request: {method} (id={expected_id})")
        
        # Wait for response
        start = time.time()
        mismatched_responses = 0
        
        while time.time() - start < timeout:
            try:
                response = self.response_queue.get(timeout=self.config.poll_interval)
                response_id = response.get("id")
                
                if response_id == expected_id:
                    logger.debug(f"Received response for {method} (id={expected_id})")
                    return response
                else:
                    mismatched_responses += 1
                    logger.debug(f"Mismatched response id: {response_id} (expected {expected_id})")
            except queue.Empty:
                continue
        
        # Timeout - flush orphaned responses
        flushed = 0
        while not self.response_queue.empty():
            try:
                orphan = self.response_queue.get_nowait()
                flushed += 1
                logger.debug(f"Flushed orphaned response: {orphan.get('id')}")
            except queue.Empty:
                break
        
        error_msg = f"Request {method} timed out after {timeout}s"
        if mismatched_responses > 0:
            error_msg += f" (mismatched: {mismatched_responses}, flushed: {flushed})"
        raise LSPTimeoutError(error_msg)
    
    def _send_notification(self, method: str, params: Dict):
        """Send a notification to the language server (no response expected)."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        body = json.dumps(message)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        
        self.process.stdin.write((header + body).encode())
        self.process.stdin.flush()
        
        logger.debug(f"Sent notification: {method}")
    
    def _initialize(self):
        """Initialize the language server."""
        init_options = self.get_init_options()
        
        params = {
            "processId": os.getpid(),
            "rootUri": f"file://{self.project_path}",
            "capabilities": {},
            "clientInfo": {"name": "lsp-client", "version": "1.0"},
            "workspaceFolders": [{
                "uri": f"file://{self.project_path}",
                "name": os.path.basename(self.project_path)
            }]
        }
        
        if init_options:
            params["initializationOptions"] = init_options
        
        self._send_request("initialize", params, timeout=20)
        self._send_notification("initialized", {})
        
        logger.info("LSP server initialized")
    
    def open_document(self, file_path: str, content: str):
        """Notify the server that a document has been opened."""
        self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": f"file://{file_path}",
                "languageId": self.get_language_id(),
                "version": 1,
                "text": content
            }
        })
    
    def goto_definition(self, file_path: str, line: int, character: int, retries: Optional[int] = None) -> List[Dict]:
        """
        Request definition location for a symbol.
        
        Args:
            file_path: File path
            line: Line number (0-based)
            character: Character position (0-based)
            retries: Number of retries (uses config default if not specified)
            
        Returns:
            List of location dictionaries
        """
        params = {
            "textDocument": {"uri": f"file://{file_path}"},
            "position": {"line": line, "character": character}
        }
        
        response = self._send_request("textDocument/definition", params, retries=retries)
        result = response.get("result", [])
        
        if isinstance(result, dict):
            return [result]
        return result or []
    
    def goto_implementation(self, file_path: str, line: int, character: int) -> List[Dict]:
        """Request implementation locations for a symbol."""
        params = {
            "textDocument": {"uri": f"file://{file_path}"},
            "position": {"line": line, "character": character}
        }
        
        response = self._send_request("textDocument/implementation", params)
        result = response.get("result", [])
        
        if isinstance(result, dict):
            return [result]
        return result or []
    
    def goto_type_definition(self, file_path: str, line: int, character: int, retries: Optional[int] = None) -> List[Dict]:
        """Request type definition locations for a symbol."""
        params = {
            "textDocument": {"uri": f"file://{file_path}"},
            "position": {"line": line, "character": character}
        }
        
        response = self._send_request("textDocument/typeDefinition", params, retries=retries)
        result = response.get("result", [])
        
        if isinstance(result, dict):
            return [result]
        return result or []
    
    def get_references(self, file_path: str, line: int, character: int) -> List[Dict]:
        """Get references to a symbol."""
        params = {
            "textDocument": {"uri": f"file://{file_path}"},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True}
        }
        
        response = self._send_request("textDocument/references", params)
        return response.get("result", [])
    
    def find_references(self, file_path: str, line: int, character: int) -> Dict:
        """
        Find references with standardized output format for focal method enricher.
        
        Returns:
            Dictionary with 'references' key containing list of references
        """
        raw_refs = self.get_references(file_path, line, character)
        if not raw_refs:
            return {'references': []}
        
        references = []
        for ref in raw_refs:
            ref_uri = ref.get('uri', '')
            ref_path = ref_uri.replace('file://', '')
            ref_range = ref.get('range', {})
            references.append({
                'file_path': ref_path,
                'range': ref_range
            })
        
        return {'references': references}
    
    def close(self):
        """Shut down the language server."""
        if self.process is None:
            return
        
        # Signal threads to stop
        self.stop_event.set()
        
        try:
            # Try graceful shutdown
            if self.process.poll() is None:
                try:
                    self._send_request("shutdown", {}, timeout=5)
                    self._send_notification("exit", {})
                except Exception as e:
                    logger.warning(f"Error during shutdown request: {e}")
                
                # Wait for process to exit gracefully
                try:
                    self.process.wait(timeout=5)
                    logger.info("LSP server shut down gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("LSP server did not exit gracefully, forcing termination")
                    self.process.kill()
                    self.process.wait(timeout=2)
        except Exception as e:
            logger.error(f"Shutdown error: {e}")
            # Force kill as last resort
            try:
                if self.process.poll() is None:
                    self.process.kill()
            except Exception:
                pass
        finally:
            # Clean up resources
            if self.process:
                for pipe in [self.process.stdin, self.process.stdout, self.process.stderr]:
                    if pipe:
                        try:
                            pipe.close()
                        except Exception:
                            pass
            
            # Join threads with timeout
            if self.reader_thread and self.reader_thread.is_alive():
                self.reader_thread.join(timeout=2)
            if self.stderr_thread and self.stderr_thread.is_alive():
                self.stderr_thread.join(timeout=2)
            
            self.process = None
            self.reader_thread = None
            self.stderr_thread = None
            self.stop_event.clear()
