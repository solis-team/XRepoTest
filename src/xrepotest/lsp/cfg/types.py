"""
CFG type definitions and data structures.

Ported from LSPRAG TypeScript implementation.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node


class CFGNodeType(Enum):
    """Types of nodes in the control flow graph"""
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    STATEMENT = "STATEMENT"
    CONDITION = "CONDITION"
    LOOP = "LOOP"
    BLOCK = "BLOCK"
    MERGED = "MERGED"
    EXIT_MERGED = "EXIT_MERGED"
    BREAK = "BREAK"
    CONTINUE = "CONTINUE"
    RETURN = "RETURN"
    TRY = "TRY"
    CATCH = "CATCH"
    FINALLY = "FINALLY"


@dataclass
class CFGNode:
    """Node in the control flow graph"""
    id: str
    text: str
    type: CFGNodeType
    ast_node: 'Node'
    successors: List['CFGNode'] = field(default_factory=list)
    predecessors: List['CFGNode'] = field(default_factory=list)
    
    # For conditions/branches
    true_block: Optional['CFGNode'] = None
    false_block: Optional['CFGNode'] = None
    condition: Optional[str] = None
    
    # Loop markers
    is_loop_back_edge: bool = False
    is_loop_break: bool = False
    is_loop_continue: bool = False


@dataclass
class LoopContext:
    """Context information for a loop during CFG construction"""
    node: CFGNode
    break_nodes: List[CFGNode] = field(default_factory=list)
    continue_nodes: List[CFGNode] = field(default_factory=list)
    exit_merged_node: Optional[CFGNode] = None


@dataclass
class ControlFlowGraph:
    """Complete control flow graph with entry and exit points"""
    entry: CFGNode
    exit: CFGNode
    nodes: dict
    language: str


@dataclass
class PathSegment:
    """Segment of an execution path"""
    code: str
    condition: Optional[str] = None


@dataclass
class PathResult:
    """Result of path traversal through CFG"""
    code: str
    path: str  # "where (\n\t<condition1>\n\t<condition2>\n)"
    simple: str  # "condition1 && condition2"


@dataclass
class ConditionAnalysis:
    """Analysis of a conditional branch in the code"""
    condition: str
    depth: int
    dependencies: Set[str] = field(default_factory=set)
    complexity: int = 0
    minimum_path_to_condition: List[PathResult] = field(default_factory=list)
