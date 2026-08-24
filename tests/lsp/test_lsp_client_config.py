import pytest

from xrepotest.lsp.exceptions import LSPConfigurationError
from xrepotest.lsp.lsp_client.base_lsp import LSPConfig
from xrepotest.lsp.lsp_client import config as lsp_config


@pytest.mark.parametrize(
    ("project_path", "expected_wait"),
    [
        ("/repos/burn-main", 120.0),
        ("/repos/BURN", 120.0),
        ("/repos/rust-master", 60.0),
        ("/repos/starship", 60.0),
        ("/repos/alacritty", 60.0),
        ("/repos/ripgrep", 45.0),
        ("/repos/small-project", 30.0),
    ],
)
def test_calculate_rust_index_wait(project_path, expected_wait):
    assert lsp_config.calculate_rust_index_wait(project_path) == expected_wait


def test_build_lsp_config_returns_defaults_for_non_rust_language():
    config = lsp_config.build_lsp_config("go")

    assert isinstance(config, LSPConfig)
    assert config.startup_wait == 2.0
    assert config.index_wait == 15.0
    assert config.request_timeout == 10.0
    assert config.retry_count == 2
    assert config.enable_retry is True


def test_build_lsp_config_for_rust_uses_calculated_wait_when_project_path_given(monkeypatch):
    def fake_calculate_rust_index_wait(project_path):
        assert project_path == "/repos/rust-repo"
        return 99.0

    monkeypatch.setattr(lsp_config, "calculate_rust_index_wait", fake_calculate_rust_index_wait)

    config = lsp_config.build_lsp_config("rust", project_path="/repos/rust-repo")

    assert config.index_wait == 99.0


def test_build_lsp_config_raises_for_unsupported_language():
    with pytest.raises(LSPConfigurationError) as exc_info:
        lsp_config.build_lsp_config("unsupported")

    assert "No LSP configuration registered for language: unsupported" in str(exc_info.value)
