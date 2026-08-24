import pytest

from xrepotest.languages import (
    LANGUAGE_CONFIGS,
    get_language_config,
    get_supported_languages,
    has_mutation_support,
)


@pytest.mark.parametrize("language_key", list(LANGUAGE_CONFIGS.keys()))
def test_get_language_config_is_case_insensitive(language_key):
    config_upper = get_language_config(language_key.upper())
    config_mixed = get_language_config(language_key.capitalize())

    assert config_upper == LANGUAGE_CONFIGS[language_key]
    assert config_mixed == LANGUAGE_CONFIGS[language_key]


def test_get_language_config_raises_for_unsupported_language_with_supported_names():
    with pytest.raises(ValueError) as exc_info:
        get_language_config("unsupported-lang")

    message = str(exc_info.value)
    assert "Unsupported language: unsupported-lang" in message
    for supported_language in LANGUAGE_CONFIGS:
        assert supported_language in message


def test_get_supported_languages_returns_language_config_keys():
    assert get_supported_languages() == list(LANGUAGE_CONFIGS.keys())


@pytest.mark.parametrize(
    "language_key",
    [name for name, config in LANGUAGE_CONFIGS.items() if config.mutation_tool],
)
def test_has_mutation_support_true_for_languages_with_mutation_tool(language_key):
    assert has_mutation_support(language_key) is True
