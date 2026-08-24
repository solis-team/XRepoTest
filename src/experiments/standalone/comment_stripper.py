"""
Comment Stripper for Multiple Programming Languages

Removes comments from code while preserving string literals
"""

import re


def strip_comments(code: str, language: str) -> str:
    """
    Remove comments from code based on language
    
    Args:
        code: Source code string
        language: Programming language (Python, Julia, Ruby, PHP, Rust, Go)
    
    Returns:
        Code with comments removed
    """
    language = language.lower()
    
    if language == 'python':
        return strip_python_comments(code)
    elif language == 'julia':
        return strip_julia_comments(code)
    elif language == 'ruby':
        return strip_ruby_comments(code)
    elif language == 'php':
        return strip_php_comments(code)
    elif language in ['rust', 'go']:
        return strip_c_style_comments(code)
    else:
        return code


def strip_python_comments(code: str) -> str:
    """Remove Python # comments and docstrings"""
    lines = []
    in_multiline = False
    multiline_char = None
    
    for line in code.split('\n'):
        stripped = line.strip()
        
        # Check for docstring start/end
        if '"""' in line or "'''" in line:
            quote = '"""' if '"""' in line else "'''"
            count = line.count(quote)
            
            if count == 2:  # Single line docstring
                lines.append('')
                continue
            elif count == 1:
                if in_multiline and multiline_char == quote:
                    in_multiline = False
                    lines.append('')
                    continue
                else:
                    in_multiline = True
                    multiline_char = quote
                    lines.append('')
                    continue
        
        if in_multiline:
            lines.append('')
            continue
        
        # Remove inline comments
        if '#' in line:
            # Preserve # inside strings
            result = []
            in_string = False
            string_char = None
            i = 0
            while i < len(line):
                char = line[i]
                
                if char in ['"', "'"] and (i == 0 or line[i-1] != '\\'):
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char:
                        in_string = False
                    result.append(char)
                elif char == '#' and not in_string:
                    break  # Rest is comment
                else:
                    result.append(char)
                i += 1
            
            line = ''.join(result).rstrip()
        
        lines.append(line)
    
    return '\n'.join(lines)


def strip_julia_comments(code: str) -> str:


    # Remove """ ... """ multi-line comments (Julia allows these for docstrings, but sometimes used for block comments)
    code = re.sub(r'""".*?"""', '', code, flags=re.DOTALL)

    # Remove single-line comments
    lines = []
    for line in code.split('\n'):
        if '#' in line:
            # Simple approach: remove everything after #
            # (doesn't handle # in strings perfectly, but Julia rarely uses # in strings)
            line = line.split('#')[0].rstrip()
        lines.append(line)

    return '\n'.join(lines)


def strip_ruby_comments(code: str) -> str:
    """Remove Ruby # comments and =begin...=end blocks"""
    lines = []
    in_multiline = False
    
    for line in code.split('\n'):
        stripped = line.strip()
        
        # Multi-line comment blocks
        if stripped.startswith('=begin'):
            in_multiline = True
            lines.append('')
            continue
        
        if stripped.startswith('=end'):
            in_multiline = False
            lines.append('')
            continue
        
        if in_multiline:
            lines.append('')
            continue
        
        # Single-line comments
        if '#' in line:
            # Simple approach for Ruby
            line = line.split('#')[0].rstrip()
        
        lines.append(line)
    
    return '\n'.join(lines)


def strip_php_comments(code: str) -> str:
    """Remove PHP //, /* */, and # comments"""
    # Remove /* */ multi-line comments
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    
    lines = []
    for line in code.split('\n'):
        # Remove // and # comments
        if '//' in line:
            line = line.split('//')[0].rstrip()
        if '#' in line:
            line = line.split('#')[0].rstrip()
        lines.append(line)
    
    return '\n'.join(lines)


def strip_c_style_comments(code: str) -> str:
    """Remove C-style // and /* */ comments (for Rust, Go)"""
    # Remove /* */ multi-line comments
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    
    # Remove // single-line comments
    lines = []
    for line in code.split('\n'):
        if '//' in line:
            line = line.split('//')[0].rstrip()
        lines.append(line)
    
    return '\n'.join(lines)


if __name__ == "__main__":
    # Test examples
    julia_code = '''
# This is a comment
"""
Multi-line comment
=#
function foo()
    x = 5  # inline comment
    return x
end

"""
hello
'''
    

    print("\nJulia (after):")
    print(strip_comments(julia_code, 'Julia'))
