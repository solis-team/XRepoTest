"""
Control Flow Graph (CFG) module for LSP-based context enrichment.

Implements CFG-based token filtering as described in the LSPRAG paper:
- Build CFG from focal method source code
- Extract execution paths and conditional branches
- Filter tokens to only those appearing in conditions
- Reduces LSP queries by 40-70% while maintaining context quality
"""

from xrepotest.lsp.cfg.types import (
    CFGNode,
    CFGNodeType,
    ControlFlowGraph,
    LoopContext,
    PathResult,
    PathSegment,
    ConditionAnalysis
)

from xrepotest.lsp.cfg.builder import CFGBuilder
from xrepotest.lsp.cfg.golang import GolangCFGBuilder
from xrepotest.lsp.cfg.python import PythonCFGBuilder
from xrepotest.lsp.cfg.rust import RustCFGBuilder
from xrepotest.lsp.cfg.ruby import RubyCFGBuilder
from xrepotest.lsp.cfg.php import PHPCFGBuilder
from xrepotest.lsp.cfg.julia import JuliaCFGBuilder
from xrepotest.lsp.cfg.path import Path, PathCollector
from xrepotest.lsp.cfg.builder_factory import CFGBuilderFactory

__all__ = [
    'CFGNode',
    'CFGNodeType',
    'ControlFlowGraph',
    'LoopContext',
    'PathResult',
    'PathSegment',
    'ConditionAnalysis',
    'CFGBuilder',
    'GolangCFGBuilder',
    'PythonCFGBuilder',
    'RustCFGBuilder',
    'RubyCFGBuilder',
    'PHPCFGBuilder',
    'JuliaCFGBuilder',
    'Path',
    'PathCollector',
    'CFGBuilderFactory'
]
