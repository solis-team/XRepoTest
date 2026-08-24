"""
Julia-specific Error Classifier

Handles Julia errors including method dispatch, type stability, and module loading issues.
"""

import re
from typing import Dict, List, Optional
from experiments.analysis.error_analysis.classifiers.base import (
    ErrorClassifier, ErrorCategory, ErrorDetails, 
    ClassificationResult, UNDEFINED_PATTERNS, ASSERTION_KEYWORDS
)


class JuliaErrorClassifier(ErrorClassifier):
    """Classifier for Julia test generation errors"""
    
    def __init__(self):
        super().__init__("julia")
    
    def _classify_single(self, log: str, check: Dict, coverage_stat: Dict, test_code: str) -> ClassificationResult:
        """
        Override classification for Julia (interpreted/JIT language).
        
        In Julia, checks['compilation'] only means syntax check passed,
        NOT that type checking was done. Type errors appear at runtime.
        
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
        # Julia is dynamically typed - compilation only checks syntax, not types/APIs
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
        # NOTE: In Julia, all type/API errors happen at runtime
        if not tests_success:
            # Check for API Hallucination
            result = self._detect_api_hallucination(log, test_code)
            if result:
                return result
            
            # Check for Type System & Memory errors (happen at runtime in Julia)
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
        """Initialize Julia-specific regex patterns"""
        return {
            'syntax_error': [
                re.compile(r'syntax:', re.IGNORECASE),
                re.compile(r'ParseError', re.IGNORECASE),
                re.compile(r'unexpected.*in input', re.IGNORECASE),
            ],
            'method_error': [
                re.compile(r'MethodError:', re.IGNORECASE),
                re.compile(r'no method matching', re.IGNORECASE),
            ],
            'type_error': [
                re.compile(r'TypeError:', re.IGNORECASE),
                re.compile(r'type.*has no field', re.IGNORECASE),
                re.compile(r'cannot convert', re.IGNORECASE),
                re.compile(r'BoundsError:', re.IGNORECASE),
                re.compile(r'InexactError:', re.IGNORECASE),
                re.compile(r'DivideError:', re.IGNORECASE),
            ],
            'undefined_error': [
                re.compile(r'UndefVarError:', re.IGNORECASE),
                re.compile(r'not defined', re.IGNORECASE),
            ],
            'argument_error': [
                re.compile(r'ArgumentError:', re.IGNORECASE),
                re.compile(r'DimensionMismatch', re.IGNORECASE),
            ],
            'load_error': [
                re.compile(r'LoadError:', re.IGNORECASE),
                re.compile(r'ERROR: LoadError:', re.IGNORECASE),
            ],
            'test_fail': [
                re.compile(r'Test Failed', re.IGNORECASE),
                re.compile(r'@test', re.IGNORECASE),
                re.compile(r'fail.*=.*[1-9]', re.IGNORECASE),  # fail count > 0
            ],
        }
    
    def _detect_syntax_error(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect Julia syntax errors"""
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
        
        # Check for LoadError which often indicates syntax issues
        if 'LoadError' in log and 'syntax' in log.lower():
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.90
                )
            )
        
        return None
    
    def _detect_type_memory_error(self, log: str, test_code: str, 
                                   is_compilation: bool) -> Optional[ClassificationResult]:
        """Detect Julia type system errors"""
        confidence = 0.90 if is_compilation else 0.80
        
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
        
        # Check for MethodError (type dispatch issue)
        if self._match_pattern(log, self.patterns['method_error']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.TYPE_SYSTEM_MEMORY,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.85
                )
            )
        
        # Check for ArgumentError (can indicate type issues)
        if self._match_pattern(log, self.patterns['argument_error']):
            # ArgumentError is often about wrong types or dimensions
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.TYPE_SYSTEM_MEMORY,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.75
                )
            )
        
        return None
    
    def _detect_api_hallucination(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect API hallucination in Julia"""
        # Check for UndefVarError (undefined variables/functions)
        if self._match_pattern(log, self.patterns['undefined_error']):
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
        
        # Check for LoadError with module/import issues
        if self._match_pattern(log, self.patterns['load_error']):
            error_msg = self._extract_first_error(log)
            # If it mentions missing modules or functions
            if any(keyword in error_msg.lower() for keyword in 
                   ['not defined', 'not found', 'cannot find']):
                return ClassificationResult(
                    has_error=True,
                    error_category=ErrorCategory.API_HALLUCINATION,
                    error_details=ErrorDetails(
                        line_number=self._extract_line_number(log),
                        error_message=error_msg,
                        full_log=log,
                        confidence=0.80
                )
            )
        
        # Check for "no method matching" - could be hallucinated function signature
        if 'no method matching' in log.lower():
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
        
        # Generic undefined patterns
        if self._match_pattern(log, UNDEFINED_PATTERNS):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.API_HALLUCINATION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.70
                )
            )
        
        return None
    
    def _detect_logic_assertion_error(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect Julia test logic and assertion errors"""
        # Check for test failure patterns
        if self._match_pattern(log, self.patterns['test_fail']):
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
        
        # Parse test counts from log (if available)
        # Format: pass=X, fail=Y, error=Z, broken=W
        fail_match = re.search(r'fail\s*=\s*([1-9]\d*)', log, re.IGNORECASE)
        if fail_match:
            fail_count = int(fail_match.group(1))
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.LOGIC_ASSERTION,
                error_details=ErrorDetails(
                    error_message=f"Test failures detected: {fail_count} test(s) failed",
                    confidence=0.95
                )
            )
        
        # Check for assertion keywords
        if self._contains_keywords(log, ASSERTION_KEYWORDS + ['@test', 'Test Failed']):
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
        """Detect Julia test design issues"""
        # Check for hardcoded values in @test assertions
        hardcoded_patterns = [
            re.compile(r'@test.*==.*"hardcoded"', re.IGNORECASE),
            re.compile(r'@test.*≈.*1\.23456789', re.IGNORECASE),  # Overly precise float
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
        """Override to handle Julia-specific line number formats"""
        # Julia format: @ filename.jl:123
        julia_pattern = re.search(r'@.*?:(\d+)', log)
        if julia_pattern:
            return int(julia_pattern.group(1))
        
        # Fall back to base implementation
        return super()._extract_line_number(log)
