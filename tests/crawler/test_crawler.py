from pathlib import Path

from xrepotest.crawler import crawler as crawler_module


def test_resolve_config_path_prefers_direct_path(monkeypatch):
    config_name = "config.json"
    module_candidate = Path(crawler_module.__file__).resolve().parent / config_name
    project_candidate = Path("/project-root") / config_name

    monkeypatch.setattr(crawler_module, "get_project_root", lambda: Path("/project-root"))

    existing = {str(Path(config_name)), str(module_candidate), str(project_candidate)}

    def fake_is_file(self):
        return str(self) in existing

    monkeypatch.setattr(Path, "is_file", fake_is_file)

    assert crawler_module.resolve_config_path(config_name) == str(Path(config_name))


def test_resolve_config_path_uses_module_relative_if_direct_missing(monkeypatch):
    config_name = "config.json"
    module_candidate = Path(crawler_module.__file__).resolve().parent / config_name
    project_candidate = Path("/project-root") / config_name

    monkeypatch.setattr(crawler_module, "get_project_root", lambda: Path("/project-root"))

    existing = {str(module_candidate), str(project_candidate)}

    def fake_is_file(self):
        return str(self) in existing

    monkeypatch.setattr(Path, "is_file", fake_is_file)

    assert crawler_module.resolve_config_path(config_name) == str(module_candidate)


def test_resolve_config_path_uses_project_root_fallback(monkeypatch):
    config_name = "config.json"
    project_candidate = Path("/project-root") / config_name

    monkeypatch.setattr(crawler_module, "get_project_root", lambda: Path("/project-root"))

    existing = {str(project_candidate)}

    def fake_is_file(self):
        return str(self) in existing

    monkeypatch.setattr(Path, "is_file", fake_is_file)

    assert crawler_module.resolve_config_path(config_name) == str(project_candidate)
