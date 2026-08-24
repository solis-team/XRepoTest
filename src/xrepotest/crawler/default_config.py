"""
Crawler config loading utilities.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_crawler_config(config_path: str) -> Dict[str, Any]:
    """Load crawler config from a JSON file."""
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Crawler config file not found: {config_path}")

    with open(path, "r", encoding="utf-8") as fh:
        config = json.load(fh)

    if not isinstance(config, dict):
        raise ValueError(f"Crawler config must be a JSON object: {config_path}")

    return config
