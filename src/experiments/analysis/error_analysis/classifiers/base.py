"""
Base Error Classifier Framework for LLM-Generated Unit Tests

This module provides the abstract base class and shared utilities for 
classifying errors in LLM-generated test code across multiple programming languages.
"""

import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class ErrorCategory(Enum):
    """5-category taxonomy for test generation errors"""
    SYNTACTIC_COMPILATION = "Syntactic & Compilation"
    TYPE_SYSTEM_MEMORY = "Type System & Memory"
    API_HALLUCINATION = "API Hallucination"
    LOGIC_ASSERTION = "Logic & Assertion"
    TEST_DESIGN_MOCKING = "Test Design & Mocking"


@dataclass
class ErrorDetails:
    """Structured error information"""
    line_number: Optional[int] = None
    error_message: str = ""
    full_log: str = ""  # Complete log for detailed analysis
    code_snippet: str = ""
    confidence: float = 1.0  # 0.0 to 1.0


@dataclass
class ClassificationResult:
    """Output of error classification"""
    has_error: bool
    error_category: Optional[ErrorCategory] = None
    error_details: Optional[ErrorDetails] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "has_error": self.has_error,
            "error_category": self.error_category.value if self.error_category else None,
            "error_details": None
        }
        
        if self.error_details:
            result["error_details"] = {
                "line_number": self.error_details.line_number,
                "error_message": self.error_details.error_message,
                "full_log": self.error_details.full_log,
                "code_snippet": self.error_details.code_snippet,
                "confidence": self.error_details.confidence
            }
        
        return result


class ErrorClassifier(ABC):
    """Abstract base class for language-specific error classifiers"""
    
    def __init__(self, language: str):
        self.language = language
        self.patterns = self._initialize_patterns()
    
    @abstractmethod
    def _initialize_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Initialize language-specific regex patterns"""
        pass
    
    def classify(self, logs: List[str], checks: List[Dict],
                 coverage_stats: List[Dict], test_code: List[str]) -> List[ClassificationResult]:
        """
        Classify errors for all tests in a sample.
        
        Args:
            logs: List of log strings, one per test
            checks: List of check dicts with compilation/tests/coverage flags
            coverage_stats: List of coverage stat dicts
            test_code: List of test code strings
            
        Returns:
            List of ClassificationResult, one per test
        """
        results = []
        
        for i in range(len(test_code)):
            log = logs[i] if i < len(logs) else ""
            check = checks[i] if i < len(checks) else {}
            coverage_stat = coverage_stats[i] if i < len(coverage_stats) else {}

            result = self._classify_single(log, check, coverage_stat, test_code[i])
            results.append(result)
        
        return results
    
    def _classify_single(self, log: str, check: Dict, coverage_stat: Dict, test_code: str) -> ClassificationResult:
        """
        Classify error for a single test following priority order.
        
        Priority:
        0. No test extracted (preprocessing error) -> Category 1
        1. Compilation failed -> Check Cat3, Cat2, Cat1
        2. Compilation passed but tests failed -> Check Cat4, Cat2 (runtime)
        3. All passed -> Check Cat5 (design anti-patterns)
        """
        # Handle preprocessing errors (no test extracted)
        if log and "preprocessing" in log.lower() and "no tests generated" in log.lower():
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                error_details=ErrorDetails(
                    error_message="Test extraction failed during preprocessing - likely syntax error in generated code",
                    confidence=0.85
                )
            )
        
        # Handle empty test case (no test code provided)
        # This happens when preprocessing filters out invalid test syntax
        if not test_code or (not log and not check):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                error_details=ErrorDetails(
                    error_message="No test code provided - likely filtered during preprocessing due to syntax error",
                    confidence=0.80
                )
            )
        
        compilation_success = check.get("compilation", False)
        tests_success = check.get("tests", check.get("test", False))
        
        # Step 1: Check compilation status
        if not compilation_success:
            # Priority: Category 3 > Category 2 > Category 1
            
            # Check for API Hallucination (Category 3)
            result = self._detect_api_hallucination(log, test_code)
            if result:
                return result
            
            # Check for Type System & Memory (Category 2)
            result = self._detect_type_memory_error(log, test_code, is_compilation=True)
            if result:
                return result
            
            # Check for Syntactic & Compilation (Category 1)
            result = self._detect_syntax_error(log, test_code)
            if result:
                return result
            
            # Fallback: Compilation failed but no specific pattern matched
            if log:
                return ClassificationResult(
                    has_error=True,
                    error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                    error_details=ErrorDetails(
                        error_message=self._extract_first_error(log),
                        confidence=0.5
                    )
                )
            else:
                # No log but compilation failed
                return ClassificationResult(
                    has_error=True,
                    error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                    error_details=ErrorDetails(
                        error_message="Compilation failed with no output",
                        confidence=0.3
                    )
                )
        
        # Step 2: Compilation passed but tests failed
        if compilation_success and not tests_success:
            # Check for runtime type errors (Category 2)
            result = self._detect_type_memory_error(log, test_code, is_compilation=False)
            if result:
                return result
            
            # Check for logic & assertion errors (Category 4)
            result = self._detect_logic_assertion_error(log, test_code)
            if result:
                return result
            
            # Fallback: Test failed but no specific pattern
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.LOGIC_ASSERTION,
                error_details=ErrorDetails(
                    error_message=self._extract_first_error(log) or "Test execution failed",
                    confidence=0.5
                )
            )
        
        # Step 3: All passed - check for design issues
        if compilation_success and tests_success:
            no_coverage_result = self._detect_no_coverage_design_issue(check, coverage_stat)
            if no_coverage_result:
                return no_coverage_result

            result = self._detect_design_issues(log, test_code)
            if result:
                return result
            
            # No errors detected
            return ClassificationResult(has_error=False)
        
        # Edge case: Unknown state
        return ClassificationResult(has_error=False)

    def _detect_no_coverage_design_issue(self, check: Dict, coverage_stat: Dict) -> Optional[ClassificationResult]:
        """Detect likely design/invocation issues when tests pass but cover no focal lines.

        Heuristic used in xrepotest error analysis:
        - If tests passed and coverage succeeded, but covered_lines is 0 (most langs)
          this often indicates the test didn't execute the focal function.
        - For Ruby, the coverage pipeline can produce a minimal non-zero count; treat
          covered_lines <= 1 as equivalent.
        """
        coverage_ok = check.get("coverage", False)
        if not coverage_ok or not isinstance(coverage_stat, dict) or not coverage_stat:
            return None

        covered_lines_raw = coverage_stat.get("covered_lines")
        if covered_lines_raw is None:
            return None

        try:
            covered_lines = int(covered_lines_raw)
        except (TypeError, ValueError):
            return None

        threshold = 1 if self.language == "ruby" else 0
        if covered_lines <= threshold:
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.TEST_DESIGN_MOCKING,
                error_details=ErrorDetails(
                    error_message=(
                        f"Tests and coverage succeeded but focal coverage is too low "
                        f"(covered_lines={covered_lines}). Likely missing invocation of the focal function."
                    ),
                    confidence=0.65
                )
            )

        return None
    
    @abstractmethod
    def _detect_syntax_error(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect syntax and compilation errors (Category 1)"""
        pass
    
    @abstractmethod
    def _detect_type_memory_error(self, log: str, test_code: str, 
                                   is_compilation: bool) -> Optional[ClassificationResult]:
        """Detect type system and memory errors (Category 2)"""
        pass
    
    @abstractmethod
    def _detect_api_hallucination(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect API hallucination errors (Category 3)"""
        pass
    
    @abstractmethod
    def _detect_logic_assertion_error(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect logic and assertion errors (Category 4)"""
        pass
    
    @abstractmethod
    def _detect_design_issues(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect test design and mocking issues (Category 5)"""
        pass
    
    # Shared utility methods
    
    def _extract_line_number(self, log: str) -> Optional[int]:
        """Extract line number from error message"""
        # Common patterns: "line 42", ":42:", "line:42"
        patterns = [
            r'line[:\s]+(\d+)',
            r':(\d+):',
            r'at line (\d+)',
            r'\[line (\d+)\]'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, log, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return None
    
    def _extract_first_error(self, log: str) -> str:
        """Extract the first error message from log"""
        if not log:
            return ""
        
        # Split by newlines and find first non-empty line with error indicator
        lines = log.split('\n')
        for line in lines:
            line = line.strip()
            if any(keyword in line.lower() for keyword in 
                   ['error', 'failed', 'exception', 'panic', 'fatal']):
                return line[:200]  # Truncate very long lines
        
        # If no error keyword, return first non-empty line
        for line in lines:
            if line.strip():
                return line.strip()[:200]
        
        return ""
    
    def _extract_code_snippet(self, log: str, test_code: str, 
                              line_number: Optional[int]) -> str:
        """Extract code snippet around error location"""
        if not line_number or not test_code:
            return ""
        
        lines = test_code.split('\n')
        if line_number <= 0 or line_number > len(lines):
            return ""
        
        # Get 2 lines before and after (if available)
        start = max(0, line_number - 3)
        end = min(len(lines), line_number + 2)
        
        snippet_lines = lines[start:end]
        return '\n'.join(snippet_lines)
    
    def _match_pattern(self, log: str, patterns: List[re.Pattern]) -> Optional[re.Match]:
        """Check if any pattern matches the log"""
        for pattern in patterns:
            match = pattern.search(log)
            if match:
                return match
        return None
    
    def _contains_keywords(self, log: str, keywords: List[str]) -> bool:
        """Check if log contains any of the keywords (case-insensitive)"""
        log_lower = log.lower()
        return any(keyword.lower() in log_lower for keyword in keywords)


# Shared pattern definitions
TIMEOUT_PATTERNS = [
    re.compile(r'timeout', re.IGNORECASE),
    re.compile(r'timed out', re.IGNORECASE),
    re.compile(r'time limit exceeded', re.IGNORECASE),
]

UNDEFINED_PATTERNS = [
    re.compile(r'undefined', re.IGNORECASE),
    re.compile(r'not defined', re.IGNORECASE),
    re.compile(r'not found', re.IGNORECASE),
    re.compile(r'cannot find', re.IGNORECASE),
    re.compile(r'does not exist', re.IGNORECASE),
    re.compile(r'unresolved', re.IGNORECASE),
]

ASSERTION_KEYWORDS = [
    'assertion failed',
    'expected',
    'actual',
    'assert',
    'mismatch',
    'should equal',
    'should be',
    'to eq',
    'to equal',
]
