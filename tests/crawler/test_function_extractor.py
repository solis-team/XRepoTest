import json

from xrepotest.crawler.extractors.function_extractor import FunctionExtractor
from xrepotest.crawler.models import FunctionMetadata


class DummyLanguageParser:
    def parse(self, code: str, language: str):
        return object()


def _make_function_metadata(file_path: str) -> FunctionMetadata:
    focal_code = """
fn compute_value(a: i32) -> i32 {
    let b = a + 1;
    let c = b + 1;
    let d = c + 1;
    let e = d + 1;
    let f = e + 1;
    let g = f + 1;
    let h = g + 1;
    let i = h + 1;
    i
}
""".strip()

    return FunctionMetadata(
        function_name="compute_value",
        file_path=file_path,
        focal_code=focal_code,
        file_content=focal_code,
        language="rust",
        function_component={
            "name": "compute_value",
            "signature": "fn compute_value(a: i32) -> i32",
            "start_line": 1,
            "end_line": 11,
        },
        metadata={},
    )


def _make_config(tmp_path, repo_filter_rules=None):
    config_path = tmp_path / "config.json"
    config = {
        "filter_rules": {
            "rust": {
                "min_lines": 1,
                "max_lines": 200,
                "exclude_patterns": [],
                "exclude_prefixes": [],
                "source_roots": ["src", "lib"],
            }
        }
    }
    if repo_filter_rules is not None:
        config["repo_filter_rules"] = repo_filter_rules
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return str(config_path)


def test_filter_function_accepts_nested_source_root_segment(tmp_path):
    extractor = FunctionExtractor(DummyLanguageParser(), _make_config(tmp_path))
    metadata = _make_function_metadata("tokio/tokio/src/runtime/task/mod.rs")

    assert extractor.filter_function(metadata) is True


def test_filter_function_rejects_path_without_source_root_segment(tmp_path):
    extractor = FunctionExtractor(DummyLanguageParser(), _make_config(tmp_path))
    metadata = _make_function_metadata("tokio/tokio-macros/macros/entry.rs")

    assert extractor.filter_function(metadata) is False


def test_repo_source_root_override_can_disable_source_root_filter(tmp_path):
    extractor = FunctionExtractor(
        DummyLanguageParser(),
        _make_config(
            tmp_path,
            repo_filter_rules={
                "rust": {
                    "edge-repo": {
                        "source_roots": [],
                    }
                }
            },
        ),
    )
    metadata = _make_function_metadata("edge-repo/tools/build.rs")

    assert extractor.filter_function(metadata) is True


def test_repo_source_root_override_applies_only_to_target_repo(tmp_path):
    extractor = FunctionExtractor(
        DummyLanguageParser(),
        _make_config(
            tmp_path,
            repo_filter_rules={
                "rust": {
                    "edge-repo": {
                        "source_roots": [],
                    }
                }
            },
        ),
    )
    metadata = _make_function_metadata("other-repo/tools/build.rs")

    assert extractor.filter_function(metadata) is False


def test_repo_source_root_override_matches_repo_name_case_insensitively(tmp_path):
    extractor = FunctionExtractor(
        DummyLanguageParser(),
        _make_config(
            tmp_path,
            repo_filter_rules={
                "rust": {
                    "Edge-Repo": {
                        "source_roots": [],
                    }
                }
            },
        ),
    )
    metadata = _make_function_metadata("edge-repo/tools/build.rs")

    assert extractor.filter_function(metadata) is True
