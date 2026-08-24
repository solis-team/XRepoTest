import json

import pytest

from xrepotest.crawler.default_config import load_crawler_config


def test_load_crawler_config_reads_json_object(tmp_path):
    config_path = tmp_path / "config.json"
    expected = {
        "file_extensions": {"go": [".go"]},
        "test_patterns": {"exclude_paths": [], "exclude_files": []},
        "exclude_functions": [],
        "filter_rules": {"go": {"min_lines": 1, "max_lines": 10}},
    }
    config_path.write_text(json.dumps(expected), encoding="utf-8")

    assert load_crawler_config(str(config_path)) == expected


def test_load_crawler_config_raises_for_missing_file(tmp_path):
    missing_path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError):
        load_crawler_config(str(missing_path))


def test_load_crawler_config_raises_for_non_object_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(ValueError):
        load_crawler_config(str(config_path))
