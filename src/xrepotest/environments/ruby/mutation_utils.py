"""
Mutation testing utilities for Ruby using Mutant
"""

import subprocess
import re
import yaml
from pathlib import Path
from typing import Tuple, Dict, Any, Optional


def extract_class_and_method_from_ruby(file_path: str, method_name: str, project_path: str = None) -> Tuple[Optional[str], str]:
    """
    Extract the full class name and method type from a Ruby file using tree-sitter
    
    Args:
        file_path: Path to Ruby file (e.g., 'lib/httparty/cookie_hash.rb')
        method_name: Method name to find (e.g., 'add_cookies')
        project_path: Optional base path to prepend to file_path
    
    Returns:
        tuple: (full_class_name, method_type) 
               e.g., ('HTTParty::CookieHash', '#') or ('Capybara', '.')
    """
    try:
        import tree_sitter_ruby as tsruby
        from tree_sitter import Language, Parser
        
        RUBY_LANGUAGE = Language(tsruby.language())
    except ImportError:
        print("⚠️  tree-sitter-ruby not available, falling back to simple parsing")
        return None, '#'
    
    # Build full file path
    if project_path:
        full_path = Path(project_path) / file_path
    else:
        full_path = Path(file_path)
    
    if not full_path.exists():
        print(f"⚠️  File not found: {full_path}")
        return None, '#'
    
    # Create parser
    parser = Parser(RUBY_LANGUAGE)
    
    # Read and parse file
    with open(full_path, 'rb') as f:
        source_code = f.read()
    
    tree = parser.parse(source_code)
    root_node = tree.root_node
    
    # Track module/class nesting and find method
    def find_method_in_node(node, current_namespaces):
        # Check module
        if node.type == 'module':
            module_name = None
            for child in node.children:
                if child.type == 'constant':
                    module_name = source_code[child.start_byte:child.end_byte].decode('utf-8')
                    break
            
            if module_name:
                new_namespaces = current_namespaces + [module_name]
                for child in node.children:
                    result = find_method_in_node(child, new_namespaces)
                    if result:
                        return result
        
        # Check class
        elif node.type == 'class':
            class_name = None
            for child in node.children:
                if child.type == 'constant':
                    class_name = source_code[child.start_byte:child.end_byte].decode('utf-8')
                    break
                elif child.type == 'scope_resolution':
                    # Handle namespaced class: HTTParty::CookieHash
                    scope_text = source_code[child.start_byte:child.end_byte].decode('utf-8')
                    parts = scope_text.split('::')
                    new_namespaces = current_namespaces + parts
                    for sibling in node.children:
                        result = find_method_in_node(sibling, new_namespaces)
                        if result:
                            return result
                    return None
            
            if class_name:
                new_namespaces = current_namespaces + [class_name]
                for child in node.children:
                    result = find_method_in_node(child, new_namespaces)
                    if result:
                        return result
        
        # Check instance method
        elif node.type == 'method':
            for child in node.children:
                if child.type == 'identifier':
                    found_method = source_code[child.start_byte:child.end_byte].decode('utf-8')
                    if found_method == method_name:
                        return (current_namespaces, '#')
                    break
        
        # Check class method (singleton_method)
        elif node.type == 'singleton_method':
            for child in node.children:
                if child.type == 'identifier':
                    found_method = source_code[child.start_byte:child.end_byte].decode('utf-8')
                    if found_method == method_name:
                        return (current_namespaces, '.')
                    break
        
        # Recursively search all children
        for child in node.children:
            result = find_method_in_node(child, current_namespaces)
            if result:
                return result
        
        return None
    
    # Find the method
    result = find_method_in_node(root_node, [])
    
    if result:
        namespaces, method_type = result
        full_class = '::'.join(namespaces) if namespaces else None
        return full_class, method_type
    
    return None, '#'


def normalize_file_path(file_path: str) -> str:
    """
    Normalize file path for use in mutation testing
    
    Args:
        file_path: e.g., 'repo_name/lib/file.rb' or 'lib/file.rb'
    
    Returns:
        Normalized path (e.g., 'lib/file.rb')
    """
    normalized = file_path.replace('\\', '/')
    
    # Extract path after repository name
    if '/lib/' in normalized:
        return 'lib/' + normalized.split('/lib/', 1)[1]
    elif '/src/' in normalized:
        return 'src/' + normalized.split('/src/', 1)[1]
    
    # If already normalized
    if normalized.startswith('lib/') or normalized.startswith('src/'):
        return normalized
    
    # Extract just the last meaningful part
    parts = normalized.split('/')
    for i, part in enumerate(parts):
        if part in ['lib', 'src']:
            return '/'.join(parts[i:])
    
    return normalized


def extract_test_path(file_path: str) -> str:
    """
    Convert source file path to test file path
    
    Args:
        file_path: e.g., 'lib/file.rb'
    
    Returns:
        Test file path (e.g., 'spec/file_spec.rb')
    """
    normalized = file_path.replace('\\', '/')
    
    # Remove repo name prefix if present
    if 'lib/' in normalized:
        after_lib = normalized.split('lib/', 1)[1]
        base_name = after_lib.replace('.rb', '')
        return f'spec/{base_name}_spec.rb'
    
    # Fallback
    parts = normalized.split('/')
    filename = parts[-1].replace('.rb', '')
    return f'spec/{filename}_spec.rb'


def run_mutation_testing(
    test_file_path: str,
    focal_file_path: str,
    focal_function_name: str,
    project_root: str,
    wrap_class: str = None,
    timeout: int = 300
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Run mutation testing using Mutant for Ruby.
    
    Args:
        test_file_path: Path to the test file (e.g., 'spec/cookie_hash_spec.rb')
        focal_file_path: Path to the focal file (e.g., 'lib/httparty/cookie_hash.rb')
        focal_function_name: Name of the method to mutate (e.g., 'add_cookies')
        project_root: Root directory of the Ruby project
        wrap_class: Fallback class name if tree-sitter extraction fails
        timeout: Timeout in seconds
    
    Returns:
        Tuple[bool, Optional[Dict]]: (success, mutation_results)
    """
    project_path = Path(project_root)
    config_file = project_path / 'mutant.yml'
    
    # Initialize result
    result_dict = {
        "mutation_score": 0.0,
        "killed_count": 0,
        "escaped_count": 0,
        "timeout_count": 0,
        "total_count": 0,
        "coverage_percent": 0.0,
        "error_message": ""
    }
    
    try:
        # Normalize focal file path (strips repo prefix, keeps lib/... or src/...)
        filter_file = normalize_file_path(focal_file_path)

        # Compute test path relative to project root so mutant.yml requires work correctly.
        # normalize_file_path doesn't handle spec/ paths, so derive it from project_path instead.
        if test_file_path:
            test_path = Path(test_file_path)
            if test_path.is_absolute():
                test_filter = str(test_path.relative_to(project_path.resolve())).replace('\\', '/')
            else:
                test_filter = str(test_path).replace('\\', '/')
        else:
            test_filter = extract_test_path(focal_file_path)
        
        # Extract subject using tree-sitter
        full_class, method_type = extract_class_and_method_from_ruby(
            filter_file,
            focal_function_name,
            project_root
        )
        
        # Fallback to wrap_class if tree-sitter fails
        if not full_class and wrap_class:
            full_class = wrap_class
            method_type = '#'  # Default to instance method
        
        if not full_class:
            result_dict["error_message"] = f"Could not extract class for method '{focal_function_name}' from file: {filter_file}"
            return False, result_dict
        
        # Build subject
        subject = f"{full_class}{method_type}{focal_function_name}"
        
        print(f"[DEBUG] Mutant subject: {subject}")
        print(f"[DEBUG] Filter file: {filter_file}")
        print(f"[DEBUG] Test filter: {test_filter}")
        
        # Create Mutant config
        # Only require the generated test file to isolate mutation testing to just our test
        config = {
            'integration': 'rspec',
            'matcher': {
                'subjects': [subject]
            },
            'includes': ['spec', 'lib'],
            'requires': ['./spec/spec_helper.rb', f'./{test_filter}'],
            'jobs': 4,
            'usage': 'opensource'
        }
        
        # Write config file
        with open(config_file, 'w') as f:
            yaml.dump(config, f)
        
        # Build command
        cmd = ['bundle', 'exec', 'mutant', 'run']
        
        print(f"[DEBUG] Mutation command: {' '.join(cmd)}")
        print(f"[DEBUG] Working directory: {project_path}")
        
        # Run mutant
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(project_path),
            timeout=timeout
        )
        
        # Parse output
        output = result.stdout
        
        # Parse the summary section using regex to handle Mutant's formatted output
        # (e.g. "- Mutations    : 12" or "Mutations: 12")
        for line in output.split('\n'):
            m = re.search(r'Mutations\s*:\s*(\d+)', line)
            if m:
                result_dict['total_count'] = int(m.group(1))
                continue
            m = re.search(r'Kills\s*:\s*(\d+)', line)
            if m:
                result_dict['killed_count'] = int(m.group(1))
                continue
            m = re.search(r'Alive\s*:\s*(\d+)', line)
            if m:
                result_dict['escaped_count'] = int(m.group(1))
                continue
            m = re.search(r'Timeouts\s*:\s*(\d+)', line)
            if m:
                result_dict['timeout_count'] = int(m.group(1))
                continue
            m = re.search(r'Coverage\s*:\s*([\d.]+)', line)
            if m:
                result_dict['coverage_percent'] = float(m.group(1))

        # Calculate mutation score (0.0–1.0 scale, consistent with Go/Rust)
        if result_dict['total_count'] > 0:
            result_dict['mutation_score'] = result_dict['killed_count'] / result_dict['total_count']
        
        # Clean up config file
        if config_file.exists():
            config_file.unlink()
        
        if result_dict['total_count'] == 0:
            result_dict["error_message"] = "No mutations generated for the specified method"
            return False, result_dict
        
        return True, result_dict
        
    except subprocess.TimeoutExpired:
        result_dict["error_message"] = f"Mutation testing timeout (exceeded {timeout} seconds)"
        if config_file.exists():
            config_file.unlink()
        return False, result_dict
    except FileNotFoundError:
        result_dict["error_message"] = "Mutant not found. Install with: gem install mutant-rspec"
        if config_file.exists():
            config_file.unlink()
        return False, result_dict
    except Exception as e:
        result_dict["error_message"] = f"Mutation testing error: {e}"
        if config_file.exists():
            config_file.unlink()
        return False, result_dict
