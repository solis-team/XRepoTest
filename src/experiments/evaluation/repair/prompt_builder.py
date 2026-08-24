"""
Prompt Builder for Iterative Repair

Constructs language-specific repair prompts that include error context,
focal code, and repair instructions for the LLM.
"""

from typing import Dict


class PromptBuilder:
    def __init__(self, language: str):
        """
        Initialize prompt builder.

        Args:
            language: Programming language (go, rust, julia, php, ruby)
        """
        self.language = language.lower()
        self._init_language_config()

    def _init_language_config(self):
        """Initialize language-specific configuration"""
        self.system_prompts = {
            "go": "You are an expert Go programmer specializing in writing robust, idiomatic test cases.",
            "rust": "You are an expert Rust programmer specializing in writing correct, memory-safe test cases.",
            "julia": "You are an expert Julia programmer specializing in writing efficient, type-stable test cases.",
            "php": "You are an expert PHP programmer specializing in writing comprehensive PHPUnit test cases.",
            "ruby": "You are an expert Ruby programmer specializing in writing thorough Minitest test cases."
        }

    def build_repair_prompt(
        self,
        failed_test: str,
        error_log: str
    ) -> Dict[str, str]:
        """
        Build repair prompt for LLM.

        Args:
            failed_test: The test code that failed
            error_log: Error output from evaluation

        Returns:
            Dictionary with 'system' and 'user' prompts
        """
        # Build user prompt
        user_prompt = self._build_user_prompt(
            failed_test=failed_test,
            error_log=error_log
        )

        # Get system prompt
        system_prompt = self.get_system_prompt()

        return {
            "system": system_prompt,
            "user": user_prompt
        }

    def _build_user_prompt(
        self,
        failed_test: str,
        error_log: str
    ) -> str:
        """Build the user prompt content"""
        return f"""You previously generated a test for {self.language.title()} code that failed. Please fix the test based on the error below.

YOUR PREVIOUS TEST (FAILED):
```{self.language}
{failed_test}
```

{error_log}

OUTPUT REQUIREMENTS:
- Generate ONLY the corrected test code
- Enclose the code in markdown code blocks (e.g., ```{self.language} ... ```)
- DO NOT include explanations, comments, or non-test code before or after
- The test should be complete and ready to run
- Fix the specific error without changing unrelated parts unnecessarily

"""

    def get_system_prompt(self) -> str:
        """Get language-specific system prompt"""
        return self.system_prompts.get(
            self.language,
            "You are an expert programmer specializing in writing comprehensive test cases."
        )
