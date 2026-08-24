
#!/usr/bin/env python3
"""
Data models for the crawler
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class FunctionComponent:
    """Represents function metadata."""
    name: str
    signature: str
    start_line: int
    end_line: int


@dataclass
class FunctionMetadata:
    """Complete function metadata following the xrepotest schema."""
    function_name: str
    file_path: str
    focal_code: str
    file_content: str
    language: str
    function_component: FunctionComponent
    metadata: Dict[str, Any]  # Language-specific metadata (package, class_name, class_signature)
