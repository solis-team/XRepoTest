from openai import OpenAI
import time

from experiments.evaluation.common.result_contract import GenerationResult, error_result, success_result
from experiments.evaluation.llm.config import (
    LLM_DEFAULT_MODEL,
    LLM_DEFAULT_TEMPERATURE,
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_USER_AGENT,
)
from xrepotest.config import API_KEY

# Models (or model families) whose API rejects `max_tokens` and requires
# `max_completion_tokens` instead (e.g. OpenAI's o1/o3 and GPT-5 series).
_MAX_COMPLETION_TOKENS_MARKERS = ("gpt-5", "o1", "o3", "o4")


def _uses_max_completion_tokens(model: str) -> bool:
    model_name = model.rsplit("/", 1)[-1].lower()
    return any(marker in model_name for marker in _MAX_COMPLETION_TOKENS_MARKERS)


class OpenAIClient:
    """
    OpenAI API client wrapper with retry logic and rate limiting.
    """
    def __init__(self, api_key=None, base_url=None, delay=0, max_retries=3, retry_delay=1.0):
        self.api_key = api_key
        if not self.api_key:
            # Fallback to the key hardcoded (via file) in xrepotest.config
            self.api_key = API_KEY

        if not self.api_key:
            raise ValueError(
                "OpenAI API key must be provided or readable from xrepotest.config.API_KEY_FILE"
            )
        
        self.base_url = base_url
        
        # Only set custom headers for ramclouds.me
        default_headers = None
        if self.base_url and "ramclouds.me" in self.base_url:
            default_headers = {"User-Agent": LLM_DEFAULT_USER_AGENT}
            
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=default_headers
        )
        self.delay = delay
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def generate_result(
        self,
        prompt,
        system_prompt=None,
        model=None,
        temperature=None,
        max_tokens=None,
        **kwargs
    ) -> GenerationResult:
        """Send a prompt and return a typed generation result."""
        # Use config defaults if not provided
        model = model or LLM_DEFAULT_MODEL
        temperature = temperature if temperature is not None else LLM_DEFAULT_TEMPERATURE
        max_tokens = max_tokens or LLM_DEFAULT_MAX_TOKENS
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        token_param = "max_completion_tokens" if _uses_max_completion_tokens(model) else "max_tokens"

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    top_p=1,
                    **{token_param: max_tokens},
                    **kwargs
                )
                # Add delay to avoid rate limits
                if self.delay > 0:
                    time.sleep(self.delay)
                
                content = response.choices[0].message.content
                if content is None:
                    print(f"  Warning: Received None content from API. Response: {response}")
                    return success_result("", attempts=attempt + 1)
                if content == "":
                    print(f"  Note: Received empty string content from API.")
                return success_result(content, attempts=attempt + 1)
            
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # Check if it's a rate limit or server error that we should retry
                should_retry = any([
                    "rate_limit" in error_str.lower(),
                    "429" in error_str,
                    "500" in error_str,
                    "502" in error_str,
                    "503" in error_str,
                    "504" in error_str,
                    "timeout" in error_str.lower(),
                    "connection" in error_str.lower()
                ])
                
                if should_retry and attempt < self.max_retries - 1:
                    # Exponential backoff: wait longer after each retry
                    wait_time = self.retry_delay * (2 ** attempt)
                    print(f"  Retry {attempt + 1}/{self.max_retries - 1} after error: {error_str}")
                    print(f"  Waiting {wait_time:.1f} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    # Don't retry for other errors or if max retries reached
                    break
        
        return error_result(
            f"Error after {self.max_retries} attempts: {str(last_error)}",
            attempts=self.max_retries,
        )

    def generate(
        self,
        prompt,
        system_prompt=None,
        model=None,
        temperature=None,
        max_tokens=None,
        **kwargs
    ) -> str:
        """Backward-compatible text-only API."""
        return self.generate_result(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ).response
