"""
Code Execution Module

Handles execution of code in different programming languages.
"""

import subprocess
import tempfile
import os
from typing import Tuple


class CodeRunner:
    """Executes code in various programming languages"""
    
    def __init__(self):
        self.language_configs = {
            'Ruby': {
                'extension': '.rb',
                'run_command': lambda file: ['ruby', file]
            },
            'Julia': {
                'extension': '.jl',
                'run_command': lambda file: ['julia', file]
            },
            'Go': {
                'extension': '.go',
                'run_command': lambda file: ['go', 'run', file]
            },
            'Rust': {
                'extension': '.rs',
                'compile': True
            },
            'PHP': {
                'extension': '.php',
                'run_command': lambda file: ['php', file]
            }
        }
    
    def run_code(self, code: str, language: str, timeout: int = 5) -> Tuple[bool, str, str]:
        """
        Execute code and return (success, stdout, stderr)
        
        Args:
            code: The code to execute
            language: Programming language
            timeout: Execution timeout in seconds
            
        Returns:
            Tuple of (success, stdout, stderr)
        """
        if language not in self.language_configs:
            return False, "", f"Unsupported language: {language}"
        
        config = self.language_configs[language]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create temporary file
            file_path = os.path.join(tmpdir, f"solution{config['extension']}")
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)
            
            try:
                # Special handling for Rust (needs compilation)
                if language == 'Rust':
                    return self._run_rust(file_path, tmpdir, timeout)
                else:
                    # Run directly
                    cmd = config['run_command'](file_path)
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=tmpdir
                    )
                
                success = result.returncode == 0
                return success, result.stdout, result.stderr
                
            except subprocess.TimeoutExpired:
                return False, "", f"Execution timeout ({timeout}s)"
            except Exception as e:
                return False, "", str(e)
    
    def _run_rust(self, file_path: str, tmpdir: str, timeout: int) -> Tuple[bool, str, str]:
        """Compile and run Rust code"""
        # Compile
        compile_result = subprocess.run(
            ['rustc', file_path, '-o', os.path.join(tmpdir, 'solution')],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if compile_result.returncode != 0:
            return False, "", compile_result.stderr
        
        # Run
        result = subprocess.run(
            [os.path.join(tmpdir, 'solution')],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return result.returncode == 0, result.stdout, result.stderr
    
    def validate_syntax(self, code: str, language: str) -> Tuple[bool, str]:
        """
        Validate code syntax without running it
        
        Args:
            code: Code to validate
            language: Programming language
            
        Returns:
            Tuple of (valid, error_message)
        """
        if language not in self.language_configs:
            return False, f"Unsupported language: {language}"
        
        config = self.language_configs[language]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, f"test{config['extension']}")
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)
            
            try:
                if language == 'Ruby':
                    result = subprocess.run(
                        ['ruby', '-c', file_path],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                elif language == 'Go':
                    result = subprocess.run(
                        ['gofmt', '-e', file_path],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                elif language == 'Rust':
                    result = subprocess.run(
                        ['rustc', '--crate-type', 'lib', file_path],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        cwd=tmpdir
                    )
                elif language == 'PHP':
                    result = subprocess.run(
                        ['php', '-l', file_path],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                elif language == 'Julia':
                    # Julia doesn't have a separate syntax check, try parsing
                    result = subprocess.run(
                        ['julia', '-e', f'include("{file_path}")'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                else:
                    return True, ""  # No syntax check available
                
                return result.returncode == 0, result.stderr
                
            except Exception as e:
                return False, str(e)
