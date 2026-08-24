"""
Go-specific Error Classifier

Handles Go compiler errors, panic/runtime errors, and test failures.
"""

import re
from typing import Dict, List, Optional
from experiments.analysis.error_analysis.classifiers.base import (
    ErrorClassifier, ErrorCategory, ErrorDetails, 
    ClassificationResult, UNDEFINED_PATTERNS, ASSERTION_KEYWORDS
)


class GoErrorClassifier(ErrorClassifier):
    """Classifier for Go test generation errors"""
    
    def __init__(self):
        super().__init__("go")
    
    def _initialize_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Initialize Go-specific regex patterns"""
        return {
            'undefined': [
                re.compile(r'undefined:', re.IGNORECASE),
                re.compile(r'not defined', re.IGNORECASE),
                re.compile(r'undeclared name', re.IGNORECASE),
            ],
            'type_error': [
                re.compile(r'cannot use.*as.*in', re.IGNORECASE),
                re.compile(r'cannot convert', re.IGNORECASE),
                re.compile(r'type.*is not an expression', re.IGNORECASE),
                re.compile(r'invalid operation', re.IGNORECASE),
                re.compile(r'mismatched types', re.IGNORECASE),
            ],
            'import_error': [
                re.compile(r'imported (and|but) not used', re.IGNORECASE),
                re.compile(r'cannot find package', re.IGNORECASE),
                re.compile(r'no required module provides package', re.IGNORECASE),
            ],
            'syntax_error': [
                re.compile(r'syntax error', re.IGNORECASE),
                re.compile(r'expected.*found', re.IGNORECASE),
                re.compile(r'unexpected.*at end', re.IGNORECASE),
                re.compile(r'missing', re.IGNORECASE),
            ],
            'panic': [
                re.compile(r'panic:', re.IGNORECASE),
                re.compile(r'runtime error:', re.IGNORECASE),
                re.compile(r'nil pointer dereference', re.IGNORECASE),
                re.compile(r'index out of range', re.IGNORECASE),
                re.compile(r'send on closed channel', re.IGNORECASE),
                re.compile(r'receive on closed channel', re.IGNORECASE),
                re.compile(r'goroutine.*panic', re.IGNORECASE),
            ],
            'test_fail': [
                re.compile(r'FAIL:', re.IGNORECASE),
                re.compile(r'--- FAIL:', re.IGNORECASE),
                re.compile(r'test.*failed', re.IGNORECASE),
            ],
            'interface_error': [
                re.compile(r'does not implement', re.IGNORECASE),
                re.compile(r'missing method', re.IGNORECASE),
                re.compile(r'interface conversion', re.IGNORECASE),
            ],
            'unexported': [
                re.compile(r'cannot refer to unexported', re.IGNORECASE),
                re.compile(r'unexported field', re.IGNORECASE),
            ],
        }
    
    def _detect_syntax_error(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect Go syntax errors"""
        if self._match_pattern(log, self.patterns['syntax_error']):
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
        
        # Check for "build failed" generic error
        if 'build failed' in log.lower():
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                error_details=ErrorDetails(
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.70
                )
            )
        
        return None
    
    def _detect_type_memory_error(self, log: str, test_code: str, 
                                   is_compilation: bool) -> Optional[ClassificationResult]:
        """Detect Go type system errors"""
        confidence = 0.95 if is_compilation else 0.80
        
        # Check for type errors
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
        
        # Check for interface errors
        if self._match_pattern(log, self.patterns['interface_error']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.TYPE_SYSTEM_MEMORY,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.90
                )
            )
        
        # Runtime type panics
        if not is_compilation and self._match_pattern(log, self.patterns['panic']):
            if 'type' in log.lower() or 'interface' in log.lower():
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
        
        return None
    
    def _detect_api_hallucination(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect API hallucination in Go"""
        # Check for undefined symbols
        if self._match_pattern(log, self.patterns['undefined']):
            error_msg = self._extract_first_error(log)
            
            # Higher confidence if it's clearly an undefined function/package
            if any(keyword in error_msg.lower() for keyword in 
                   ['undefined', 'not defined', 'undeclared']):
                return ClassificationResult(
                    has_error=True,
                    error_category=ErrorCategory.API_HALLUCINATION,
                    error_details=ErrorDetails(
                        line_number=self._extract_line_number(log),
                        error_message=error_msg,
                        full_log=log,
                        confidence=0.85
                    )
                )
        
        # Check for import errors (package not found)
        if 'cannot find package' in log.lower() or 'no required module' in log.lower():
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
        
        # Check for unexported field access (trying to use private fields)
        if self._match_pattern(log, self.patterns['unexported']):
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
        """Detect Go test logic and assertion errors"""
        # Check for test failure messages
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
        
        # Check for panic that's not type-related (likely logic error)
        if self._match_pattern(log, self.patterns['panic']):
            error_msg = self._extract_first_error(log)
            # If panic message contains assertion-like keywords
            if self._contains_keywords(error_msg, ASSERTION_KEYWORDS):
                return ClassificationResult(
                    has_error=True,
                    error_category=ErrorCategory.LOGIC_ASSERTION,
                    error_details=ErrorDetails(
                        line_number=self._extract_line_number(log),
                        error_message=error_msg,
                        full_log=log,
                        confidence=0.85
                    )
                )
        
        # Check for assertion keywords
        if self._contains_keywords(log, ASSERTION_KEYWORDS):
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
        """Detect Go test design issues"""
        # Check for hardcoded values
        hardcoded_patterns = [
            re.compile(r'if.*!=.*"hardcoded"', re.IGNORECASE),
            re.compile(r't\.Errorf.*expected.*123', re.IGNORECASE),
        ]
        
        if self._match_pattern(test_code, hardcoded_patterns):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.TEST_DESIGN_MOCKING,
                error_details=ErrorDetails(
                    error_message="Test contains hardcoded values in assertions",
                    confidence=0.50
                )
            )
        
        # Note: Removed unused imports check - it's a compiler warning, not a design issue
        
        return None
