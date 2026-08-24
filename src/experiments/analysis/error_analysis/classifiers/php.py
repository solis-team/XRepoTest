"""
PHP-specific Error Classifier

Handles PHP syntax errors, fatal errors, and PHPUnit test failures.
"""

import re
from typing import Dict, List, Optional
from experiments.analysis.error_analysis.classifiers.base import (
    ErrorClassifier, ErrorCategory, ErrorDetails, 
    ClassificationResult, UNDEFINED_PATTERNS, ASSERTION_KEYWORDS
)


class PHPErrorClassifier(ErrorClassifier):
    """Classifier for PHP test generation errors"""
    
    def __init__(self):
        super().__init__("php")
    
    def _classify_single(self, log: str, check: Dict, coverage_stat: Dict, test_code: str) -> ClassificationResult:
        """
        Override classification for PHP (interpreted language).
        
        In PHP, checks['compilation'] only means syntax check passed (php -l),
        NOT that type checking was done. Type/fatal errors appear at runtime.
        
        Modified priority:
        1. Syntax/parse errors (only pure syntax issues)
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
        # PHP is dynamically typed - compilation (php -l) only checks syntax
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
        # NOTE: In PHP, all type/API errors happen at runtime (after php -l passes)
        if not tests_success:
            # Check for API Hallucination (undefined functions/classes)
            result = self._detect_api_hallucination(log, test_code)
            if result:
                return result
            
            # Check for Type System & Memory errors (fatal errors, type errors at runtime)
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
        """Initialize PHP-specific regex patterns"""
        return {
            'syntax_error': [
                re.compile(r'Parse error:', re.IGNORECASE),
                re.compile(r'syntax error', re.IGNORECASE),
                re.compile(r'unexpected.*expecting', re.IGNORECASE),
            ],
            'fatal_error': [
                re.compile(r'Fatal error:', re.IGNORECASE),
                re.compile(r'PHP Fatal error:', re.IGNORECASE),
            ],
            'undefined': [
                re.compile(r'Call to undefined (function|method)', re.IGNORECASE),
                re.compile(r'Undefined (variable|constant|class)', re.IGNORECASE),
                re.compile(r'Class.*not found', re.IGNORECASE),
                re.compile(r'Namespace.*not found', re.IGNORECASE),
                re.compile(r'Trait.*not found', re.IGNORECASE),
            ],
            'method_exception': [
                # Runtime exceptions indicating API hallucination (high confidence)
                re.compile(r'BadMethodCallException', re.IGNORECASE),
                re.compile(r'UnknownSetterException', re.IGNORECASE),
                re.compile(r'UnknownGetterException', re.IGNORECASE),
                re.compile(r'UnknownMethodException', re.IGNORECASE),
                re.compile(r'Error:.*Call to undefined method', re.IGNORECASE),
                re.compile(r'NoMethodError', re.IGNORECASE),
                # Namespace/declaration misuse (happens at runtime despite passing php -l)
                re.compile(r'Namespace declaration statement', re.IGNORECASE),
                re.compile(r'declare.*must be the very first', re.IGNORECASE),
                re.compile(r'strict_types declaration', re.IGNORECASE),
            ],
            'property_exception': [
                # Property access errors (medium-high confidence)
                re.compile(r'Error:.*Undefined property', re.IGNORECASE),
                re.compile(r'Error:.*Attempt to read property', re.IGNORECASE),
                re.compile(r'property.*does not exist', re.IGNORECASE),
                re.compile(r'must not be accessed before initialization', re.IGNORECASE),
            ],
            'type_error': [
                re.compile(r'TypeError:', re.IGNORECASE),
                re.compile(r'Argument.*must be.*given', re.IGNORECASE),
                re.compile(r'Return value.*must be', re.IGNORECASE),
            ],
            'warning': [
                re.compile(r'Warning:', re.IGNORECASE),
                re.compile(r'PHP Warning:', re.IGNORECASE),
            ],
            'phpunit_fail': [
                # More specific patterns to avoid matching error summaries
                re.compile(r'FAILURES!', re.IGNORECASE),  # Actual test failures
                re.compile(r'Failed asserting', re.IGNORECASE),  # Assertion failures
                re.compile(r'Tests:.*Failures:.*[1-9]', re.IGNORECASE),  # Must have actual failure count
                re.compile(r'Tests:.*Assertions:', re.IGNORECASE),  # PHPUnit summary with assertions
            ],
            'autoload_error': [
                re.compile(r'failed to open stream', re.IGNORECASE),
                re.compile(r'include.*failed', re.IGNORECASE),
                re.compile(r'require.*failed', re.IGNORECASE),
            ],
        }
    
    def _detect_syntax_error(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect PHP syntax errors (only called when compilation=False)"""
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
        
        # Parse errors are syntax errors
        if 'parse error' in log.lower():
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
        
        # Compilation error prefix (generic fatal errors during php -l)
        if log.strip().startswith('Compilation error:') and 'Fatal error:' in log:
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
        """Detect PHP type errors"""
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
        
        # Fatal errors related to types
        if self._match_pattern(log, self.patterns['fatal_error']):
            error_msg = self._extract_first_error(log)
            if any(keyword in error_msg.lower() for keyword in 
                   ['type', 'argument', 'return value']):
                return ClassificationResult(
                    has_error=True,
                    error_category=ErrorCategory.TYPE_SYSTEM_MEMORY,
                    error_details=ErrorDetails(
                        line_number=self._extract_line_number(log),
                        error_message=error_msg,
                        full_log=log,
                        confidence=0.85
                    )
                )
        
        return None
    
    def _detect_api_hallucination(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect API hallucination in PHP"""
        # Check for runtime method exceptions (HIGH confidence - clear API hallucination)
        if self._match_pattern(log, self.patterns['method_exception']):
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
        
        # Check for property access exceptions (MEDIUM-HIGH confidence)
        if self._match_pattern(log, self.patterns['property_exception']):
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
        
        # Check for undefined functions/classes
        if self._match_pattern(log, self.patterns['undefined']):
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
        
        # Check for autoload errors (missing classes/files)
        if self._match_pattern(log, self.patterns['autoload_error']):
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
        
        # Generic undefined patterns (fallback with lower confidence)
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
        """Detect PHP test logic and assertion errors"""
        # Check for PHPUnit failure patterns (more specific now)
        if self._match_pattern(log, self.patterns['phpunit_fail']):
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
        if self._contains_keywords(log, ASSERTION_KEYWORDS + ['Failed asserting', 'FAILURES']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.LOGIC_ASSERTION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.85
                )
            )
        
        # Lower confidence for generic error summaries (these may be exceptions caught by PHPUnit)
        if 'ERRORS!' in log or re.search(r'There (?:was|were) \d+ errors?:', log, re.IGNORECASE):
            # Only classify as logic error if no exception patterns found (API check already ran)
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.LOGIC_ASSERTION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.60  # Lower confidence - could be exceptions
                )
            )
        
        return None
    
    def _detect_design_issues(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect PHP test design issues"""
        # Check for hardcoded values
        hardcoded_patterns = [
            re.compile(r'\$this->assertEquals\([^,]+,\s*"hardcoded"', re.IGNORECASE),
            re.compile(r'\$this->assertSame\([^,]+,\s*123\)', re.IGNORECASE),
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
        """Override to handle PHP-specific line number formats"""
        # PHP format: in /path/file.php on line 42
        php_pattern = re.search(r'on line (\d+)', log, re.IGNORECASE)
        if php_pattern:
            return int(php_pattern.group(1))
        
        # Fall back to base implementation
        return super()._extract_line_number(log)
