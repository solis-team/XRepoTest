"""
Test Code Extraction Module

Extracts test code from LLM responses that may contain explanations,
markdown formatting, code blocks, or other extraneous content.
"""

import re
from typing import Optional, Dict


class TestExtractor:
    """Extracts clean test code from LLM responses"""
    
    def __init__(self):
        self.language_patterns = {
            'Ruby': {
                'code_block': r'```(?:ruby|rb)?\s*\n(.*?)```',
                'test_keywords': ['Test', 'describe', 'it ', 'expect', 'assert', 'should'],
                'comment_prefix': '#'
            },
            'Julia': {
                'code_block': r'```(?:julia|jl)?\s*\n(.*?)```',
                'test_keywords': ['@test', '@testset', 'Test', 'using Test'],
                'comment_prefix': '#'
            },
            'Go': {
                'code_block': r'```(?:go|golang)?\s*\n(.*?)```',
                'test_keywords': ['func Test', 'testing.T', 'import "testing"'],
                'comment_prefix': '//'
            },
            'Rust': {
                'code_block': r'```(?:rust|rs)?\s*\n(.*?)```',
                'test_keywords': ['#[test]', '#[cfg(test)]', 'mod tests', 'assert!', 'assert_eq!'],
                'comment_prefix': '//'
            },
            'PHP': {
                'code_block': r'```(?:php)?\s*\n(.*?)```',
                'test_keywords': ['class Test', 'function test', 'PHPUnit', 'assert'],
                'comment_prefix': '//'
            }
        }
    
    def extract_code_blocks(self, response: str) -> list:
        """Extract all code blocks from markdown-style response"""
        # Handle non-string inputs gracefully
        if not isinstance(response, str):
            print(f"Warning: extract_code_blocks received non-string: {type(response)}")
            if response is None:
                return []
            # Try to convert to string
            response = str(response)
        
        # Match both language-specific and generic code blocks
        pattern = r'```[\w]*\s*\n(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)
        return matches
    
    def extract_test_code(self, response: str, language: str) -> str:
        """
        Extract test code from LLM response
        
        Args:
            response: Raw LLM response text
            language: Programming language (Ruby, Julia, Go, Rust, PHP)
            
        Returns:
            Cleaned test code
        """
        # Handle None or non-string inputs
        if response is None:
            return ""
        if not isinstance(response, str):
            response = str(response)
        
        if language not in self.language_patterns:
            # If language not recognized, try basic extraction
            return self._basic_extraction(response)
        
        config = self.language_patterns[language]
        
        # Step 1: Try to extract from code blocks
        code_blocks = self.extract_code_blocks(response)
        
        if code_blocks:
            # Find the block that looks most like test code
            for block in code_blocks:
                if self._looks_like_test_code(block, config['test_keywords']):
                    return self._clean_code(block, language)
            
            # If no clear test block, return the first/largest block
            if code_blocks:
                return self._clean_code(max(code_blocks, key=len), language)
        
        # Step 2: No code blocks found, try to extract raw code
        # Look for test-like patterns in the response
        lines = response.split('\n')
        code_lines = []
        in_code = False
        
        for line in lines:
            # Skip obvious explanation lines
            if self._is_explanation_line(line):
                continue
            
            # Check if line looks like code
            if self._looks_like_code_line(line, language):
                in_code = True
                code_lines.append(line)
            elif in_code and line.strip():
                code_lines.append(line)
            elif in_code and not line.strip():
                # Empty line in code block
                code_lines.append(line)
        
        if code_lines:
            return self._clean_code('\n'.join(code_lines), language)
        
        # Step 3: Last resort - return cleaned response
        return self._clean_code(response, language)
    
    def _looks_like_test_code(self, code: str, keywords: list) -> bool:
        """Check if code contains test-related keywords"""
        return any(keyword in code for keyword in keywords)
    
    def _is_explanation_line(self, line: str) -> bool:
        """Check if line is likely an explanation rather than code"""
        stripped = line.strip().lower()
        
        # Common explanation patterns
        explanation_patterns = [
            r'^here[\'s\s]',
            r'^this\s+(code|test|function)',
            r'^the\s+(code|test|function)',
            r'^explanation:',
            r'^note:',
            r'^example:',
            r'^usage:',
            r'^\d+\.',  # Numbered lists
            r'^[-*]\s',  # Bullet points
        ]
        
        return any(re.match(pattern, stripped) for pattern in explanation_patterns)
    
    def _looks_like_code_line(self, line: str, language: str) -> bool:
        """Check if line looks like code (not explanation)"""
        stripped = line.strip()
        
        if not stripped:
            return False
        
        if language in self.language_patterns:
            config = self.language_patterns[language]
            
            # Check for test keywords
            if any(keyword in line for keyword in config['test_keywords']):
                return True
        
        # Common code patterns
        code_indicators = [
            r'^\s*def\s+',  # Function definitions
            r'^\s*function\s+',
            r'^\s*class\s+',
            r'^\s*import\s+',
            r'^\s*require\s+',
            r'^\s*using\s+',
            r'^\s*package\s+',
            r'^\s*#\[',  # Rust attributes
            r'^\s*@',  # Decorators/annotations
            r'[=\(\)\{\}\[\];]',  # Common code symbols
        ]
        
        return any(re.search(pattern, stripped) for pattern in code_indicators)
    
    def _clean_code(self, code: str, language: str) -> str:
        """Clean extracted code"""
        lines = code.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Remove common artifacts
            line = line.rstrip()
            
            # Skip lines that are clearly not code
            if self._is_explanation_line(line):
                continue
            
            cleaned_lines.append(line)
        
        # Join and remove excessive blank lines
        result = '\n'.join(cleaned_lines)
        result = re.sub(r'\n{3,}', '\n\n', result)  # Max 2 consecutive blank lines
        
        return result.strip()
    
    def _basic_extraction(self, response: str) -> str:
        """Basic extraction when language is unknown"""
        # Try to extract code blocks
        code_blocks = self.extract_code_blocks(response)
        if code_blocks:
            return max(code_blocks, key=len).strip()
        
        # Return cleaned response
        return response.strip()
    
    def extract_multiple_tests(self, response: str, language: str) -> list:
        """
        Extract multiple test cases if the response contains several tests
        
        Args:
            response: Raw LLM response text
            language: Programming language
            
        Returns:
            List of test code strings
        """
        code_blocks = self.extract_code_blocks(response)
        
        if not code_blocks:
            # Single test case
            return [self.extract_test_code(response, language)]
        
        # Multiple code blocks - extract each as a test
        tests = []
        for block in code_blocks:
            cleaned = self._clean_code(block, language)
            if cleaned:
                tests.append(cleaned)
        
        return tests if tests else [self.extract_test_code(response, language)]
    
    def validate_test_code(self, code: str, language: str) -> Dict[str, any]:
        """
        Validate that extracted code looks like valid test code
        
        Args:
            code: Extracted test code
            language: Programming language
            
        Returns:
            Dict with validation results
        """
        if not code or not code.strip():
            return {
                'valid': False,
                'reason': 'Empty code',
                'confidence': 0.0
            }
        
        if language not in self.language_patterns:
            return {
                'valid': True,
                'reason': 'Unknown language, cannot validate',
                'confidence': 0.5
            }
        
        config = self.language_patterns[language]
        
        # Check for test keywords
        has_test_keywords = any(keyword in code for keyword in config['test_keywords'])
        
        # Check code length
        lines = [l for l in code.split('\n') if l.strip()]
        has_reasonable_length = len(lines) >= 3
        
        # Calculate confidence
        confidence = 0.0
        if has_test_keywords:
            confidence += 0.6
        if has_reasonable_length:
            confidence += 0.3
        if not self._is_explanation_line(code.split('\n')[0]):
            confidence += 0.1
        
        return {
            'valid': confidence >= 0.5,
            'reason': f'Test keywords: {has_test_keywords}, Length: {len(lines)} lines',
            'confidence': min(confidence, 1.0),
            'has_test_keywords': has_test_keywords,
            'line_count': len(lines)
        }


# Convenience function
def extract_test_from_response(response: str, language: str) -> str:
    """
    Quick function to extract test code from LLM response
    
    Args:
        response: Raw LLM response
        language: Programming language
        
    Returns:
        Cleaned test code
    """
    extractor = TestExtractor()
    return extractor.extract_test_code(response, language)
