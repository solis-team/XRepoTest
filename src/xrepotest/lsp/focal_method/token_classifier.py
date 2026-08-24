"""
Token Classifier Module

Classifies tokens based on their helpfulness for LLM context.
Port of LSPRAG's tokenAnalyzer.ts filtering logic.

This module provides:
- Filtering of unhelpful tokens (comments, literals, built-ins)
- Language-specific built-in type/function databases
- CFG-based filtering for condition-aware token selection
"""

import re
import logging
from typing import List, Dict, Any, Set

from xrepotest.lsp.cfg.types import ConditionAnalysis

logger = logging.getLogger(__name__)


class TokenClassifier:
    """
    Classify tokens based on their helpfulness for LLM context.
    Port of LSPRAG's tokenAnalyzer.ts filtering logic.
    """
    
    # Token types to skip (from LSPRAG tokenAnalyzer.ts)
    SKIP_TYPES = {
        "comment", "string", "number", "boolean", "null", 
        "undefined", "literal", "builtin_constant"
    }
    
    # Types that are helpful for definition context
    DEFINITION_HELPFUL_TYPES = {
        'function', 'class', 'method', 'type', 'interface',
        'struct', 'enum', 'global', 'member', 'field'
    }
    
    # Types that are helpful for reference/usage examples
    REFERENCE_HELPFUL_TYPES = {
        'function', 'method', 'parameter', 'variable'
    }
    
    def __init__(self, language: str):
        self.language = language
        self._init_language_specifics()
        self.cfg_enabled = False
        self.condition_tokens: Set[str] = set()
    
    def _init_language_specifics(self):
        """Initialize language-specific built-in types and functions to skip"""
        self.builtin_types: Set[str] = set()
        self.builtin_functions: Set[str] = set()
        
        if self.language == 'go':
            self.builtin_types = {
                # Primitives
                'int', 'int8', 'int16', 'int32', 'int64',
                'uint', 'uint8', 'uint16', 'uint32', 'uint64', 'uintptr',
                'float32', 'float64',
                'complex64', 'complex128',
                'bool', 'string', 'byte', 'rune', 'error',
                'interface{}', 'any',
                
                # Common stdlib types
                'context', 'Context',
                'Error',
                'Reader', 'Writer', 'ReadWriter', 'ReadCloser', 'WriteCloser', 'ReadWriteCloser',
                'File', 'FileInfo', 'FileMode',
                'Time', 'Duration', 'Location',
                'Mutex', 'RWMutex', 'WaitGroup', 'Once', 'Cond',
                'Channel', 'chan',
                
                # Common containers
                'map', 'slice', 'array', 'struct', 'interface', 'func',
                
                # HTTP/Net types
                'Request', 'Response', 'ResponseWriter', 'Handler', 'HandlerFunc',
                'Header', 'Cookie', 'URL',
                'Conn', 'Listener', 'Addr',
                
                # Encoding types
                'Encoder', 'Decoder', 'Marshaler', 'Unmarshaler',
                
                # Testing
                'T', 'B', 'M', 'TB',
                
                # Sync types
                'Pool', 'Map',
                
                # Bufio
                'Buffer', 'Scanner', 'BufferedReader', 'BufferedWriter',
                
                # Bytes/Strings
                'Builder',
                
                # Fmt
                'Stringer', 'Formatter', 'State', 'ScanState',
                
                # Reflect
                'Value', 'Type', 'Kind',
                
                # Other common interfaces
                'Closer', 'Seeker', 'ReaderAt', 'WriterAt',
                
                # Common stdlib package names (to skip import statements)
                'errors', 'fmt', 'strings', 'bytes', 'io', 'os', 'path', 'filepath',
                'bufio', 'encoding', 'json', 'xml', 'csv', 'base64', 'hex',
                'http', 'net', 'url', 'mail', 'smtp', 'rpc', 'textproto',
                'time', 'sync', 'atomic', 'reflect', 'regexp', 'sort', 'strconv',
                'unicode', 'utf8', 'utf16', 'math', 'rand', 'big', 'cmplx', 'bits',
                'log', 'slog', 'testing', 'flag', 'runtime', 'debug', 'pprof', 'trace',
                'container', 'heap', 'list', 'ring', 'crypto', 'hash', 'cipher',
            }
            self.builtin_functions = {
                # Built-in functions
                'len', 'cap', 'make', 'new', 'append', 'copy', 'delete', 'clear',
                'panic', 'recover', 'print', 'println',
                'complex', 'real', 'imag', 'close'
            }
        elif self.language == 'rust':
            self.builtin_types = {
                # Primitives
                'i8', 'i16', 'i32', 'i64', 'i128', 'isize',
                'u8', 'u16', 'u32', 'u64', 'u128', 'usize',
                'f32', 'f64', 'bool', 'char', 'str',
                
                # Common stdlib
                'Vec', 'VecDeque', 'LinkedList',
                'HashMap', 'HashSet', 'BTreeMap', 'BTreeSet',
                'Box', 'Rc', 'Arc', 'Cell', 'RefCell',
                'Mutex', 'RwLock', 'Cow',
                'String', 'OsString', 'PathBuf',
                'Option', 'Result',
                
                # Traits (usually don't need extraction)
                'Iterator', 'IntoIterator', 'Clone', 'Copy',
                'Debug', 'Display', 'Default',
                
                # Enum variants
                'Some', 'None', 'Ok', 'Err',
            }
            self.builtin_functions = {
                # Built-in macros (used as functions)
                'panic', 'assert', 'assert_eq', 'assert_ne',
                'debug_assert', 'debug_assert_eq', 'debug_assert_ne',
                'print', 'println', 'eprint', 'eprintln',
                'format', 'write', 'writeln',
                'vec', 'format_args', 'include', 'include_str', 'include_bytes',
                'cfg', 'env', 'option_env', 'concat', 'line', 'file', 'column',
                'stringify', 'module_path', 'todo', 'unimplemented', 'unreachable'
            }
        elif self.language == 'julia':
            self.builtin_types = {
                # Primitives
                'Int', 'Int8', 'Int16', 'Int32', 'Int64', 'Int128',
                'UInt', 'UInt8', 'UInt16', 'UInt32', 'UInt64', 'UInt128',
                'Float16', 'Float32', 'Float64',
                'Bool', 'Char', 'String',
                'Complex', 'ComplexF32', 'ComplexF64',
                'Rational',
                
                # Core types
                'Any', 'Nothing', 'Missing', 'Vararg',
                'Symbol', 'Tuple', 'NamedTuple',
                'Array', 'Vector', 'Matrix',
                'Dict', 'Set',
                'AbstractArray', 'AbstractVector', 'AbstractMatrix',
                'AbstractDict', 'AbstractSet',
                'Number', 'Real', 'Integer', 'AbstractFloat',
                
                # Common abstract types
                'AbstractString', 'IO', 'Exception',

                # Julia Base module types (commonly used, don't need LSP lookup)
                'Pair', 'Memory', 'Ref', 'Ptr', 'CFunction',
                'Channel', 'Task', 'Condition', 'Event', 'RecursiveLock',
                'ErrorException', 'ArgumentError', 'MethodError', 'LoadError',
                'Range', 'StepRange', 'UnitRange', 'LinRange',
                'BitVector', 'ByteVector', 'CharVector', 'IntVector',
                'DenseArray', 'DenseMatrix', 'DenseVector',
                'SmallVector', 'InlineVector',
                'IdDict', 'WeakDict', 'OrderedDict', 'SortedDict',
                'MutableSet', 'BitSet',
                'SubString', 'IOStream', 'IOBuffer',
                'Function', 'Method', 'Module', 'Type', 'DataType',
                'IdentityDictionary', 'IndexLinear', 'IndexCartesian',
                'ItToTuple', 'TupleToIT', 'Iterators',
                'PermutedDimsArray', 'ReshapedArray', 'ReinterpretArray',
                'CartesianIndices', 'LinearIndices',
            }
            self.builtin_functions = {
                # Built-in functions
                'print', 'println', 'show', 'display',
                'length', 'size', 'ndims', 'eltype',
                'push', 'pop', 'append', 'prepend', 'insert',
                'delete', 'splice', 'empty',
                'sort', 'sort', 'reverse', 'unique',
                'map', 'filter', 'reduce', 'foreach',
                'typeof', 'isa', 'convert', 'promote',
                'error', 'throw', 'rethrow', 'try', 'catch',
                'open', 'close', 'read', 'write', 'readlines',
                'parse', 'string', 'repr'
            }
        elif self.language == 'ruby':
            self.builtin_types = {
                # Core classes
                'Object', 'Class', 'Module',
                'String', 'Symbol', 'Integer', 'Float', 'Numeric',
                'Array', 'Hash', 'Set',
                'Range', 'Regexp',
                'TrueClass', 'FalseClass', 'NilClass',
                'Proc', 'Lambda', 'Method',
                
                # IO and Files
                'IO', 'File', 'Dir', 'Pathname',
                'StringIO', 'STDIN', 'STDOUT', 'STDERR',
                
                # Time
                'Time', 'Date', 'DateTime',
                
                # Exceptions
                'Exception', 'StandardError', 'RuntimeError', 'ArgumentError',
                'TypeError', 'NameError', 'NoMethodError',
                
                # Enumerable
                'Enumerable', 'Enumerator',
                
                # Thread/Sync
                'Thread', 'Mutex', 'Queue',
                
                # Struct
                'Struct', 'OpenStruct',
                
                # Other common
                'Binding', 'Fiber', 'ObjectSpace',
                'Random', 'Rational', 'Complex',
            }
            self.builtin_functions = {
                # Built-in functions/methods
                'puts', 'print', 'p', 'pp',
                'gets', 'readline', 'readlines',
                'raise', 'fail', 'catch', 'throw',
                'require', 'require_relative', 'load',
                'defined', 'block_given',
                'lambda', 'proc', 'eval', 'exec',
                'sleep', 'exit', 'abort', 'at_exit',
                'caller', 'binding', 'local_variables', 'global_variables',
                'rand', 'srand', 'loop', 'select'
            }
        elif self.language == 'php':
            self.builtin_types = {
                # Primitives and type hints
                'int', 'float', 'string', 'bool', 'array',
                'object', 'null', 'resource', 'callable',
                'iterable', 'mixed', 'void', 'never',
                
                # Core classes
                'stdClass', 'Exception', 'Throwable', 'Error',
                'ErrorException', 'RuntimeException', 'LogicException',
                'InvalidArgumentException', 'OutOfBoundsException',
                
                # DateTime
                'DateTime', 'DateTimeImmutable', 'DateTimeInterface',
                'DateTimeZone', 'DateInterval', 'DatePeriod',
                
                # Iterators
                'ArrayAccess', 'Iterator', 'IteratorAggregate', 'Traversable',
                'Countable', 'SeekableIterator',
                'Closure', 'Generator', 'WeakReference',
                
                # SPL Data Structures
                'ArrayObject', 'ArrayIterator', 'SplFileInfo', 'SplFileObject',
                'SplDoublyLinkedList', 'SplStack', 'SplQueue',
                'SplHeap', 'SplMaxHeap', 'SplMinHeap', 'SplPriorityQueue',
                'SplFixedArray', 'SplObjectStorage',
                
                # SPL Exceptions
                'BadFunctionCallException', 'BadMethodCallException',
                'DomainException', 'LengthException', 'OutOfRangeException',
                'OverflowException', 'RangeException', 'UnderflowException',
                'UnexpectedValueException',
                
                # Reflection
                'ReflectionClass', 'ReflectionMethod', 'ReflectionProperty',
                'ReflectionFunction', 'ReflectionParameter', 'ReflectionType',
                
                # Database (common)
                'PDO', 'PDOStatement', 'PDOException',
                'mysqli', 'mysqli_result', 'mysqli_stmt',
                
                # XML/JSON
                'SimpleXMLElement', 'DOMDocument', 'DOMElement', 'DOMNode',
                'XMLReader', 'XMLWriter',
                'JsonSerializable',
            }
            self.builtin_functions = {
                # Built-in functions (most common)
                'echo', 'print', 'var_dump', 'print_r', 'var_export',
                'die', 'exit', 'error_reporting', 'trigger_error',
                'isset', 'empty', 'unset', 'defined',
                'count', 'sizeof', 'strlen', 'is_array', 'is_string', 'is_int', 'is_bool',
                'array_push', 'array_pop', 'array_shift', 'array_unshift',
                'array_merge', 'array_slice', 'array_keys', 'array_values',
                'explode', 'implode', 'join', 'str_replace', 'substr',
                'file_get_contents', 'file_put_contents', 'fopen', 'fclose',
                'json_encode', 'json_decode', 'serialize', 'unserialize',
                'require', 'require_once', 'include', 'include_once',
                'class_exists', 'function_exists', 'method_exists'
            }
    
    def should_skip(self, token: Dict[str, Any]) -> bool:
        """Check if token should be skipped (not helpful)"""
        if not token or not token.get('type'):
            return True
        
        token_type = token['type'].lower()
        token_word = token.get('word', '').strip()
        
        # Skip empty tokens
        if not token_word:
            return True
        
        # Skip based on type
        if token_type in self.SKIP_TYPES:
            return True
        
        # Skip built-in types
        if token_word in self.builtin_types:
            return True
        
        # Skip built-in functions
        if token_word in self.builtin_functions:
            return True
        
        # Skip operators and keywords
        if self._is_operator_or_keyword(token_word):
            return True
        
        return False
    
    def _is_operator_or_keyword(self, word: str) -> bool:
        """Check if word is an operator or keyword"""
        # Common operators
        operators = {'+', '-', '*', '/', '%', '=', '==', '!=', '<', '>', 
                    '<=', '>=', '&&', '||', '!', '&', '|', '^', '~',
                    '<<', '>>', '++', '--', '+=', '-=', '*=', '/='}
        
        if word in operators:
            return True
        
        # Common keywords across languages
        keywords = {
            'if', 'else', 'for', 'while', 'return', 'break', 'continue',
            'switch', 'case', 'default', 'func', 'function', 'def', 'fn',
            'class', 'struct', 'interface', 'trait', 'impl', 'type',
            'var', 'let', 'const', 'mut', 'pub', 'private', 'public',
            'static', 'final', 'abstract', 'virtual', 'override',
            'import', 'package', 'module', 'use', 'require', 'include',
            'new', 'delete', 'nil', 'null', 'true', 'false', 'self', 'this'
        }
        
        return word.lower() in keywords
    
    def is_definition_helpful(self, token: Dict[str, Any]) -> bool:
        """
        Check if retrieving definition for this token would be helpful.
        Based on LSPRAG's defaultIsDefinitionHelpful and cfgBasedIsDefinitionHelpful.
        """
        if self.should_skip(token):
            return False
        
        token_type = token.get('type', '').lower()
        
        # Always helpful for function/method calls and type references
        if token_type in self.DEFINITION_HELPFUL_TYPES:
            return True
        
        # Note: Removed capitalization heuristic (token_word[0].isupper())
        # This caused false positives (Go exported functions, constants) 
        # and false negatives (PHP lowercase types).
        # Now relying solely on tree-sitter node type classification.
        
        return False
    
    def is_reference_helpful(self, token: Dict[str, Any]) -> bool:
        """
        Check if retrieving usage examples for this token would be helpful.
        Based on LSPRAG's defaultIsReferenceHelpful.
        """
        if self.should_skip(token):
            return False
        
        token_type = token.get('type', '').lower()
        
        # Helpful for function calls (to see usage patterns)
        if token_type in self.REFERENCE_HELPFUL_TYPES:
            return True
        
        return False
    
    def enable_cfg_filtering(self, conditions: List['ConditionAnalysis']):
        """
        Enable CFG-based filtering with extracted conditions.
        Only tokens appearing in conditions will need definitions.
        """
        self.cfg_enabled = True
        self.condition_tokens = self._extract_tokens_from_conditions(conditions)
        logger.info(f"CFG filtering enabled: {len(self.condition_tokens)} unique tokens in conditions")
        logger.debug(f"Condition tokens: {self.condition_tokens}")
    
    def _extract_tokens_from_conditions(self, conditions: List['ConditionAnalysis']) -> Set[str]:
        """Extract all identifiers from condition expressions"""
        tokens = set()
        
        for cond_analysis in conditions:
            logger.debug(f"Extracting tokens from condition: {cond_analysis.condition}")
            # Parse condition text to extract identifiers
            # Remove ALL non-alphanumeric characters except underscores
            # This handles: ., ?, ::, !, &&, ||, ==, !=, <, >, <=, >=, +, -, *, /, %
            cleaned = re.sub(r'[^a-zA-Z0-9_\s]', ' ', cond_analysis.condition)
            words = cleaned.split()
            logger.debug(f"Cleaned condition words: {words}")
            
            for word in words:
                # Filter out numbers and keywords
                if word and not word.isdigit() and not self._is_operator_or_keyword(word):
                    tokens.add(word)
                    # Also add to dependencies
                    cond_analysis.dependencies.add(word)
        
        return tokens
    
    def is_token_in_conditions(self, token_word: str) -> bool:
        """Check if token appears in any condition"""
        return token_word in self.condition_tokens
    
    def cfg_based_is_definition_helpful(self, token: Dict[str, Any]) -> bool:
        """
        CFG-based filtering - only fetch definitions for tokens in conditions.
        Based on LSPRAG's cfgBasedIsDefinitionHelpful().
        """
        if not self.cfg_enabled:
            # Fallback to default logic if CFG not enabled
            return self.is_definition_helpful(token)
        
        token_word = token.get('word', '')
        token_type = token.get('type', '').lower()
        
        # Skip if should skip anyway (includes built-in functions)
        if self.should_skip(token):
            return False
        
        # Function/method calls: include (to check return types)
        if token_type in ['function', 'method']:
            return True
        
        # Skip class definitions (too long, not helpful)
        if token_type == 'class':
            return False
        
        # Token must appear in a condition to be helpful
        if not self.is_token_in_conditions(token_word):
            return False
        
        # Additional filters from default logic
        return self.is_definition_helpful(token)
    
    def cfg_based_is_reference_helpful(self, token: Dict[str, Any]) -> bool:
        """
        CFG-based filtering for references.
        LSPRAG sets this to False - no reference examples in CFG mode.
        """
        return False
