"""
Factory to create language-specific CFG builders.
"""

from tree_sitter import Parser

from xrepotest.lsp.cfg.builder import CFGBuilder
from xrepotest.lsp.cfg.golang import GolangCFGBuilder
from xrepotest.lsp.cfg.python import PythonCFGBuilder
from xrepotest.lsp.cfg.rust import RustCFGBuilder
from xrepotest.lsp.cfg.ruby import RubyCFGBuilder
from xrepotest.lsp.cfg.php import PHPCFGBuilder
from xrepotest.lsp.cfg.julia import JuliaCFGBuilder


class CFGBuilderFactory:
    """Factory to create language-specific CFG builders"""
    
    @staticmethod
    def create_builder(language: str, parser: Parser) -> CFGBuilder:
        """Create appropriate CFG builder for the given language"""
        language = language.lower()
        
        if language == 'go':
            return GolangCFGBuilder(language, parser)
        elif language == 'python':
            return PythonCFGBuilder(language, parser)
        elif language == 'rust':
            return RustCFGBuilder(language, parser)
        elif language == 'ruby':
            return RubyCFGBuilder(language, parser)
        elif language == 'php':
            return PHPCFGBuilder(language, parser)
        elif language == 'julia':
            return JuliaCFGBuilder(language, parser)
        else:
            raise ValueError(f"No CFG builder available for language: {language}")
