"""
Rust-specific Error Classifier

Handles Rust compiler errors, borrow checker violations, and test failures.
"""

import re
from typing import Dict, List, Optional
from experiments.analysis.error_analysis.classifiers.base import (
    ErrorClassifier, ErrorCategory, ErrorDetails, 
    ClassificationResult, UNDEFINED_PATTERNS, ASSERTION_KEYWORDS
)


class RustErrorClassifier(ErrorClassifier):
    """Classifier for Rust test generation errors"""
    
    # Rust error code categorization
    BORROW_CHECKER_CODES = [
        'E0382',  # Use of moved value
        'E0502',  # Cannot borrow as mutable
        'E0499',  # Cannot borrow as mutable more than once
        'E0503',  # Cannot use as mut because also borrowed as immutable
        'E0505',  # Cannot move out of borrowed content
        'E0596',  # Cannot borrow as mutable
    ]
    
    LIFETIME_CODES = [
        'E0106',  # Missing lifetime specifier
        'E0621',  # Explicit lifetime required
        'E0623',  # Lifetime mismatch
    ]
    
    TYPE_ERROR_CODES = [
        'E0308',  # Mismatched types
        'E0277',  # Trait not implemented
        'E0282',  # Type annotations needed
        'E0283',  # Type annotations required
        'E0369',  # Binary operation cannot be applied
        'E0061',  # Wrong number of function arguments
        'E0063',  # Missing fields in struct literal
    ]
    
    UNDEFINED_CODES = [
        'E0425',  # Cannot find value
        'E0412',  # Cannot find type
        'E0433',  # Failed to resolve import
        'E0432',  # Unresolved import
        'E0599',  # No method named X found
        'E0609',  # No field X on type Y
    ]
    
    SYNTAX_CODES = [
        'E0423',  # Expected function, found module
        'E0424',  # Expected value, found module
        'E0426',  # Undeclared label
        'E0428',  # Name is defined multiple times
    ]
    
    MEMORY_SAFETY_CODES = [
        'E0507',  # Cannot move out of borrowed content
        'E0594',  # Cannot assign to immutable borrowed content
    ]
    
    def __init__(self):
        super().__init__("rust")
    
    def _initialize_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Initialize Rust-specific regex patterns"""
        return {
            'error_code': [re.compile(r'error\[E(\d+)\]')],
            'borrow_error': [
                re.compile(r'borrow of moved value', re.IGNORECASE),
                re.compile(r'cannot borrow.*as mutable', re.IGNORECASE),
                re.compile(r'use of moved value', re.IGNORECASE),
                re.compile(r'cannot move out of', re.IGNORECASE),
            ],
            'lifetime_error': [
                re.compile(r'lifetime.*required', re.IGNORECASE),
                re.compile(r'missing lifetime specifier', re.IGNORECASE),
                re.compile(r'explicit lifetime', re.IGNORECASE),
            ],
            'type_error': [
                re.compile(r'mismatched types', re.IGNORECASE),
                re.compile(r'expected.*found', re.IGNORECASE),
                re.compile(r'trait.*not implemented', re.IGNORECASE),
                re.compile(r'type annotations? (needed|required)', re.IGNORECASE),
            ],
            'syntax_error': [
                re.compile(r'unexpected token', re.IGNORECASE),
                re.compile(r'expected.*found', re.IGNORECASE),
                re.compile(r'parse error', re.IGNORECASE),
                re.compile(r'syntax error', re.IGNORECASE),
                re.compile(r'macro.*not found', re.IGNORECASE),
                re.compile(r'cannot find macro', re.IGNORECASE),
            ],
            'import_error': [
                re.compile(r'unresolved import', re.IGNORECASE),
                re.compile(r'failed to resolve', re.IGNORECASE),
                re.compile(r'no.*in scope', re.IGNORECASE),
            ],
            'panic': [
                re.compile(r'thread.*panicked', re.IGNORECASE),
                re.compile(r'panic', re.IGNORECASE),
            ],
            'assertion': [
                re.compile(r'assertion failed', re.IGNORECASE),
                re.compile(r'assert_eq!', re.IGNORECASE),
                re.compile(r'assert!', re.IGNORECASE),
            ],
        }
    
    def _detect_syntax_error(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect Rust syntax errors"""
        # Check for syntax error codes
        error_code_match = self.patterns['error_code'][0].search(log)
        if error_code_match:
            error_code = f"E{error_code_match.group(1)}"
            if error_code in self.SYNTAX_CODES:
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
        
        # Check for syntax patterns
        if self._match_pattern(log, self.patterns['syntax_error']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.SYNTACTIC_COMPILATION,
                error_details=ErrorDetails(
                    line_number=self._extract_line_number(log),
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.85
                )
            )
        
        return None
    
    def _detect_type_memory_error(self, log: str, test_code: str, 
                                   is_compilation: bool) -> Optional[ClassificationResult]:
        """Detect Rust type system and memory errors"""
        confidence = 0.95 if is_compilation else 0.80
        
        # Check for borrow checker errors
        error_code_match = self.patterns['error_code'][0].search(log)
        if error_code_match:
            error_code = f"E{error_code_match.group(1)}"
            if error_code in self.BORROW_CHECKER_CODES:
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
            if error_code in self.LIFETIME_CODES:
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
            if error_code in self.TYPE_ERROR_CODES:
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
            if error_code in self.MEMORY_SAFETY_CODES:
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
        
        # Check for pattern-based errors
        if self._match_pattern(log, self.patterns['borrow_error']):
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
        
        if self._match_pattern(log, self.patterns['lifetime_error']):
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
        
        if self._match_pattern(log, self.patterns['type_error']):
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
        """Detect API hallucination in Rust"""
        # Check for undefined error codes
        error_code_match = self.patterns['error_code'][0].search(log)
        if error_code_match:
            error_code = f"E{error_code_match.group(1)}"
            if error_code in self.UNDEFINED_CODES:
                # Check if it's likely a hallucination vs typo
                error_msg = self._extract_first_error(log)
                
                # High confidence if error mentions method/function that doesn't exist
                if any(keyword in error_msg.lower() for keyword in 
                       ['cannot find', 'unresolved', 'no method', 'no function']):
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
        
        # Check for import errors
        if self._match_pattern(log, self.patterns['import_error']):
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
        
        # Check for generic undefined patterns
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
        """Detect Rust test logic and assertion errors"""
        # Check for assertion failures
        if self._match_pattern(log, self.patterns['assertion']):
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
        
        # Check for panic (which often indicates logic errors)
        if self._match_pattern(log, self.patterns['panic']):
            # Panic due to assertion failure
            if self._contains_keywords(log, ASSERTION_KEYWORDS):
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
        
        # Check for test failure keywords
        if self._contains_keywords(log, ['test failed', 'test result: FAILED']):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.LOGIC_ASSERTION,
                error_details=ErrorDetails(
                    error_message=self._extract_first_error(log),
                    full_log=log,
                    confidence=0.70
                )
            )
        
        return None
    
    def _detect_design_issues(self, log: str, test_code: str) -> Optional[ClassificationResult]:
        """Detect Rust test design issues"""
        # Check for hardcoded values in assertions
        hardcoded_patterns = [
            re.compile(r'assert_eq!\([^,]+,\s*"hardcoded"', re.IGNORECASE),
            re.compile(r'assert_eq!\([^,]+,\s*123\)', re.IGNORECASE),
        ]
        
        if self._match_pattern(test_code, hardcoded_patterns):
            return ClassificationResult(
                has_error=True,
                error_category=ErrorCategory.TEST_DESIGN_MOCKING,
                error_details=ErrorDetails(
                    error_message="Test contains hardcoded values that may not match actual behavior",
                    confidence=0.50
                )
            )
        
        return None
