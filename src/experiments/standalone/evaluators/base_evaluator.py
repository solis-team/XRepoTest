"""
Base Language Evaluator

Abstract base class for language-specific test evaluation
"""

from abc import ABC, abstractmethod
from typing import Tuple, Optional


class LanguageEvaluator(ABC):
    """Base class for language-specific test evaluation"""
    
    def __init__(self, language: str):
        self.language = language
    
    @abstractmethod
    def get_file_extension(self) -> str:
        """Return the file extension for this language"""
        pass
    
    @abstractmethod
    def prepare_test_file(self, canonical_solution: str, test_code: str) -> str:
        """Prepare complete test file with canonical solution and test code"""
        pass
    
    @abstractmethod
    def run_tests(self, focal_file_path: str, test_file_path: str) -> Tuple[bool, str, str]:
        """
        Run tests and return (success, stdout, stderr)
        
        Args:
            focal_file_path: Path to file containing only the canonical solution
            test_file_path: Path to file containing tests (and possibly solution)
        
        Returns:
            Tuple of (test_passed, stdout, stderr)
        """
        pass
    
    @abstractmethod
    def measure_coverage(self, focal_file_path: str, test_file_path: str) -> Optional[float]:
        """
        Measure code coverage and return percentage
        
        Args:
            focal_file_path: Path to file containing only the canonical solution
            test_file_path: Path to file containing tests (and possibly solution)
        
        Returns:
            Coverage percentage (0-100) or None if measurement failed
        """
        pass
    
    def compile_if_needed(self, test_file_path: str) -> Tuple[bool, str]:
        """
        Compile code if the language requires it
        
        Returns:
            Tuple of (success, error_message)
        """
        return True, ""  # Default: no compilation needed
