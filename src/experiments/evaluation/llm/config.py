"""LLM client specific configuration."""

# LLM Client Configuration
LLM_DEFAULT_MODEL = "deepseek-v4-flash"
LLM_DEFAULT_TEMPERATURE = 0
LLM_DEFAULT_MAX_TOKENS = 4096
LLM_DEFAULT_USER_AGENT = "curl/7.68.0"

__all__ = [
    "LLM_DEFAULT_MAX_TOKENS",
    "LLM_DEFAULT_MODEL",
    "LLM_DEFAULT_TEMPERATURE",
    "LLM_DEFAULT_USER_AGENT",
]
