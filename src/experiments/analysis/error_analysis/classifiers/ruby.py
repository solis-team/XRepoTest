"""
Ruby-specific Error Classifier

Handles Ruby syntax errors, exceptions, and RSpec/Minitest failures.
"""

import re
from typing import Dict, List, Optional
from experiments.analysis.error_analysis.classifiers.base import (
    ErrorClassifier, ErrorCategory, ErrorDetails, 
    ClassificationResult, UNDEFINED_PATTERNS, ASSERTION_KEYWORDS
)


class RubyErrorClassifier(ErrorClassifier):
    """Classifier for Ruby test generation errors"""
    
    def __init__(self):
        super().__init__("ruby")
    
    def _classify_single(self, log: str, check: Dict, coverage_stat: Dict, test_code: str) -> ClassificationResult:
        """
        Override classification for Ruby (interpreted language).
        
        In Ruby, checks['compilation'] only means syntax check passed,
        NOT that type checking was done. Type/method errors appear at runtime.
        
        Modified priority:
        1. Syntax errors (only pure syntax issues)
        2. Runtime errors (type, API, logic) - regardless of 'compilation' flag
        3. Design issues if all passed
        """
        # Handle preprocessing errors
        if log and "preprocessing" in log.lower() and "no tests generated" in log.lower():
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                error_details=ErrorDetails(
                    error_message="Test extraction failed - likely syntax error",
                    confidence=0.85
                )
            )
        
        # Handle empty test case
        if not test_code or (not log and not check):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                error_details=ErrorDetails(
                    error_message="No test code - likely filtered due to syntax error",
                    confidence=0.80
                )
            )
        
        compilation_success = check.get("compilation", False)
        tests_success = check.get("tests", check.get("test", False))
        
        # Step 1: For dynamic languages, compilation=False means syntax error (Category 1)
        # Ruby is dynamically typed - compilation only checks syntax, not types/APIs
        if not compilation_success:
            syntax_result = self._detect_syntax_error(log, test_code)
            if syntax_result:
                return syntax_result
            
            # Fallback: Compilation failed but no specific syntax pattern
            if log:
                return ClassificationResult(
                    has_error=True,
                    error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                    error_details=ErrorDetails(
                        error_message=self._extract_first_error(log),
                        full_log=log,
                        confidence=0.5
                    )
                )
            else:
                return ClassificationResult(
                    has_error=True,
                    error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                    error_details=ErrorDetails(
                        error_message="Compilation failed with no output",
                        confidence=0.3
                    )
                )
        
        # Step 2: If tests failed, check runtime errors
        # NOTE: In Ruby, all type/API errors happen at runtime
        if not tests_success:
            # Check for API Hallucination (undefined methods/constants)
            result = self._detect_api_hallucination(log, test_code)
            if result:
                return result
            
            # Check for Type System & Memory errors (happen at runtime in Ruby)
            result = self._detect_type_memory_error(log, test_code, is_compilation=False)
            if result:
                return result
            
            # Check for Logic & Assertion errors
            result = self._detect_logic_assertion_error(log, test_code)
            if result:
                return result
            
            # Fallback: Test failed but no specific pattern
            if log:
                return ClassificationResult(
                    has_error=True,
                    error_category=ErrorCategory.LOGIC_ASSERTION,
                    error_details=ErrorDetails(
                        error_message=self._extract_first_error(log) or "Test execution failed",
                        full_log=log,
                        confidence=0.5
                    )
                )
        
        # Step 3: All passed - check for design issues
        if compilation_success and tests_success:
            no_coverage_result = self._detect_no_coverage_design_issue(check, coverage_stat)
            if no_coverage_result:
                return no_coverage_result
            
            # No errors detected
            return ClassificationResult(has_error=False)
        
        # No log, no failure detected
        return ClassificationResult(has_error=False)
    
    def _initialize_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Initialize Ruby-specific regex patterns"""
        return {
            'syntax_error': [
                re.compile(r'SyntaxError:', re.IGNORECASE),
                re.compile(r'syntax error', re.IGNORECASE),
                re.compile(r'unexpected.*expecting', re.IGNORECASE),
            ],
            'name_error': [
                re.compile(r'NameError:', re.IGNORECASE),
                re.compile(r'undefined (local variable|method)', re.IGNORECASE),
                re.compile(r'uninitialized constant', re.IGNORECASE),
                re.compile(r'NoMethodError:', re.IGNORECASE),
            ],
            'type_error': [
                re.compile(r'TypeError:', re.IGNORECASE),
                re.compile(r'wrong number of arguments', re.IGNORECASE),
                re.compile(r'no implicit conversion', re.IGNORECASE),                re.compile(r'IndexError:', re.IGNORECASE),
                re.compile(r'ZeroDivisionError:', re.IGNORECASE),            ],
            'argument_error': [
                re.compile(r'ArgumentError:', re.IGNORECASE),
            ],
            'load_error': [
                re.compile(r'LoadError:', re.IGNORECASE),
                re.compile(r'cannot load such file', re.IGNORECASE),
            ],
            'rspec_fail': [
                re.compile(r'expected.*to eq', re.IGNORECASE),
                re.compile(r'expected.*got', re.IGNORECASE),
                re.compile(r'Failures:', re.IGNORECASE),
                re.compile(r'\d+ example.*\d+ failure', re.IGNORECASE),
            ],
            'minitest_fail': [
                re.compile(r'Expected.*but was', re.IGNORECASE),
                re.compile(r'\d+ tests.*\d+ failures', re.IGNORECASE),
            ],
            'gem_error': [
                re.compile(r'Gem::.*Error', re.IGNORECASE),
                re.compile(r'Could not find gem', re.IGNORECASE),
            ],
        }
    
    def _detect_syntax_error(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect Ruby syntax errors"""
        if self._match_pattern(log, self.patterns['syntax_error']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.95
                )
            )
        
        return None
    
    def _detect_type_memory_error(self, log: str, test_code: str, 
                                   is_compilation: bool) -> Optional[ClassificationResult]:
        """Detect Ruby type errors"""
        confidence = 0.85 if is_compilation else 0.75
        
        # Check for TypeError
        if self._match_pattern(log, self.patterns['type_error']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.TYPE_SYSTEM_MEMORY,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=confidence
                )
            )
        
        # Check for ArgumentError (often type-related)
        if self._match_pattern(log, self.patterns['argument_error']):
            error_msg = self._extract_first_error(log)
            if 'wrong number of arguments' in error_msg.lower():
                return ClassificationResult(
                    has_error=True,
                    error_category=ErrorCategory.TYPE_SYSTEM_MEMORY,
                    error_details=ErrorDetails(
                        line_number=self._extract_line_number(log),
                        error_message=error_msg,
                        full_log=log,
                        confidence=0.80
                    )
                )
        
        return None
    
    def _detect_api_hallucination(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect API hallucination in Ruby"""
        # Check for NameError (undefined methods/constants)
        if self._match_pattern(log, self.patterns['name_error']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.API_HALLUCINATION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.90
                )
            )
        
        # Check for LoadError (missing files/gems)
        if self._match_pattern(log, self.patterns['load_error']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.API_HALLUCINATION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.85
                )
            )
        
        # Check for gem errors
        if self._match_pattern(log, self.patterns['gem_error']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.API_HALLUCINATION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.80
                )
            )
        
        # Generic undefined patterns
        if self._match_pattern(log, UNDEFINED_PATTERNS):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.API_HALLUCINATION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.75
                )
            )
        
        return None
    
    def _detect_logic_assertion_error(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect Ruby test logic and assertion errors"""
        # Check for RSpec failure patterns
        if self._match_pattern(log, self.patterns['rspec_fail']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.LOGIC_ASSERTION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.90
                )
            )
        
        # Check for Minitest failure patterns
        if self._match_pattern(log, self.patterns['minitest_fail']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.LOGIC_ASSERTION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.90
                )
            )
        
        # Check for assertion keywords
        if self._contains_keywords(log, ASSERTION_KEYWORDS + ['expected', 'Failures']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.LOGIC_ASSERTION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.80
                )
            )
        
        return None
    
    def _detect_design_issues(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect Ruby test design issues"""
        # Check for hardcoded values
        hardcoded_patterns = [
            re.compile(r'expect\([^)]+\)\.to eq\(["\']hardcoded', re.IGNORECASE),
            re.compile(r'assert_equal.*123', re.IGNORECASE),
        ]
        
        if self._match_pattern(test_code, hardcoded_patterns):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.TEST_DESIGN_MOCKING,
                error_details=ErrorDetails(
                    error_message="Test contains suspicious hardcoded values",
                    confidence=0.50
                )
            )
        
        return None
    
    def _extract_line_number(self, log: str) -> Optional[int]:
        """Override to handle Ruby-specific line number formats"""
        # Ruby format: file.rb:42:in `method'
        ruby_pattern = re.search(r'\.rb:(\d+):', log)
        if ruby_pattern:
            return int(ruby_pattern.group(1))
        
        # Fall back to base implementation
        return super()._extract_line_number(log)
