"""
Path traversal and condition analysis for CFG.

Extracts execution paths through the control flow graph and analyzes
conditional branches to identify which tokens need definitions.
"""

import re
import logging
from typing import List, Set, Dict, Optional
from xrepotest.lsp.cfg.types import CFGNode, CFGNodeType, PathSegment, PathResult, ConditionAnalysis

logger = logging.getLogger(__name__)


class Path:
    """Represents a single execution path through the CFG"""
    
    def __init__(self):
        self.segments: List[PathSegment] = []
        self.visited_loops: Dict[str, int] = {}
    
    def add_segment(self, code: str, condition: Optional[str] = None):
        """Add a segment to this path"""
        # Clean up condition text
        if condition and "((" in condition and "))" in condition:
            condition = condition.replace("((", "(").replace("))", ")")
        
        self.segments.append(PathSegment(code=code, condition=condition))
    
    def add_visited_node(self, node: CFGNode):
        """Mark a node as visited (for loop tracking)"""
        self.visited_loops[node.id] = self.visited_loops.get(node.id, 0) + 1
    
    def clone(self) -> 'Path':
        """Create a deep copy of this path"""
        new_path = Path()
        new_path.segments = list(self.segments)
        new_path.visited_loops = dict(self.visited_loops)
        return new_path
    
    def to_result(self) -> PathResult:
        """Convert to PathResult format"""
        codes = [s.code for s in self.segments if s.code]
        conditions = [s.condition for s in self.segments if s.condition]
        
        return PathResult(
            code='\n'.join(codes),
            path="where (\n\t" + '\n\t'.join(conditions) + "\n)" if conditions else "",
            simple=' && '.join(conditions) if conditions else ""
        )
    
    @property
    def condition(self) -> List[str]:
        """Get all conditions in this path"""
        return [s.condition for s in self.segments if s.condition]
    
    @property
    def length(self) -> int:
        """Get number of segments in this path"""
        return len(self.segments)


class PathCollector:
    """Traverse CFG and collect all execution paths with conditions"""
    
    def __init__(self, language: str):
        self.language = language
        self.paths: List[Path] = []
        self.visited_loops: Dict[str, int] = {}
        self.max_loop_iterations = 2
        self.condition_analysis: Dict[str, ConditionAnalysis] = {}
    
    def collect(self, cfg_entry: CFGNode) -> List[PathResult]:
        """Collect all paths from CFG entry to exit"""
        self.paths = []
        self.traverse(cfg_entry, Path())
        return [p.to_result() for p in self.paths]
    
    def traverse(self, node: CFGNode, current_path: Path):
        """Recursively traverse the CFG and collect paths"""
        # Base case 1: EXIT node - save path
        if node.type == CFGNodeType.EXIT:
            self.paths.append(current_path)
            return
        
        # Base case 2: Loop iteration limit
        visit_count = current_path.visited_loops.get(node.id, 0)
        if node.type == CFGNodeType.LOOP and visit_count >= self.max_loop_iterations:
            return
        
        # Base case 3: Back edge detection (continue statements)
        if node.is_loop_back_edge:
            return
        
        # Process node based on type
        if node.type == CFGNodeType.CONDITION:
            # Branch into two paths
            # True path
            if node.true_block:
                true_path = current_path.clone()
                true_path.add_segment(code=node.text, condition=node.condition)
                self.traverse(node.true_block, true_path)
            
            # False path
            if node.false_block:
                false_path = current_path.clone()
                false_condition = f"!({node.condition})" if node.condition else None
                false_path.add_segment(code=node.text, condition=false_condition)
                self.traverse(node.false_block, false_path)
        
        elif node.type == CFGNodeType.LOOP:
            # Mark visit
            current_path.add_visited_node(node)
            # Continue to successors
            for successor in node.successors:
                self.traverse(successor, current_path.clone())
        
        else:
            # Regular node: add to path and continue
            current_path.add_segment(code=node.text)
            for successor in node.successors:
                self.traverse(successor, current_path)
    
    def get_unique_conditions(self) -> List[ConditionAnalysis]:
        """Extract and analyze unique conditions from all paths"""
        normalized_conditions = {}
        condition_analyses: List[ConditionAnalysis] = []
        
        # Collect all paths for each condition
        condition_paths: Dict[str, List[PathResult]] = {}
        
        for path in self.paths:
            path_result = path.to_result()
            for condition in path.condition:
                if condition:
                    normalized = self.normalize_condition(condition)
                    if normalized:
                        if normalized not in condition_paths:
                            condition_paths[normalized] = []
                        condition_paths[normalized].append(path_result)
        
        # Now process each condition with its paths
        for path in self.paths:
            for condition in path.condition:
                if condition:
                    normalized = self.normalize_condition(condition)
                    if normalized and normalized not in normalized_conditions:
                        depth = self._get_condition_depth(path, condition)
                        analysis = self.analyze_condition(normalized, depth)
                        
                        # Find minimum path for this condition
                        paths = condition_paths.get(normalized, [])
                        analysis.minimum_path_to_condition = self._find_minimum_path(paths)
                        
                        condition_analyses.append(analysis)
                        normalized_conditions[normalized] = condition
        
        # Sort by complexity and depth
        return sorted(condition_analyses, key=lambda x: (x.complexity, x.depth))
    
    def normalize_condition(self, condition: str) -> str:
        """Normalize condition text for deduplication"""
        if not condition:
            return ""
        
        # Remove outer parentheses
        condition = condition.strip()
        while condition.startswith('(') and condition.endswith(')'):
            condition = condition[1:-1].strip()
        
        # Handle double negation: !(!(x)) -> x
        if condition.startswith('!(') and condition.endswith(')'):
            inner = condition[2:-1].strip()
            if inner.startswith('!(') and inner.endswith(')'):
                condition = inner[2:-1].strip()
        
        return condition if condition else ""
    
    def analyze_condition(self, condition: str, depth: int) -> ConditionAnalysis:
        """Analyze a condition to extract metadata"""
        complexity = self._calculate_complexity(condition)
        dependencies = self._extract_identifiers(condition)
        
        return ConditionAnalysis(
            condition=condition,
            depth=depth,
            dependencies=dependencies,
            complexity=complexity
        )
    
    def _calculate_complexity(self, condition: str) -> int:
        """Calculate complexity score for a condition"""
        complexity = 0
        
        # Count operators
        operators = ['+', '-', '*', '/', '%', '<', '>', '==', '!=', '<=', '>=']
        for op in operators:
            complexity += condition.count(op)
        
        # Logical operators are more complex
        complexity += condition.count('&&') * 2
        complexity += condition.count('||') * 2
        
        # Count nesting (parentheses depth)
        max_depth = 0
        current_depth = 0
        for char in condition:
            if char == '(':
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            elif char == ')':
                current_depth -= 1
        complexity += max_depth * 2
        
        return complexity
    
    def _extract_identifiers(self, condition: str) -> Set[str]:
        """Extract all identifiers from a condition"""
        # Remove operators and split
        cleaned = re.sub(r'[()!&|<>=+\-*/%]', ' ', condition)
        words = cleaned.split()
        
        identifiers = set()
        for word in words:
            # Filter out numbers and common keywords
            if word and not word.isdigit() and word not in ['true', 'false', 'null', 'nil', 'None']:
                identifiers.add(word)
        
        return identifiers
    
    def _get_condition_depth(self, path: Path, condition: str) -> int:
        """Calculate nesting depth of a condition in a path"""
        depth = 0
        for segment in path.segments:
            if segment.condition and segment.condition == condition:
                break
            if segment.condition:
                depth += 1
        return depth
    
    def _find_minimum_path(self, paths: List[PathResult]) -> List[PathResult]:
        """Find the shortest/simplest path(s) to a condition"""
        if not paths:
            return []
        
        # Score each path: fewer conditions and shorter code is better
        scored_paths = []
        for path in paths:
            condition_count = path.path.count('\n\t')
            code_length = len(path.code.split('\n'))
            score = condition_count * 10 + code_length
            scored_paths.append((score, path))
        
        # Sort by score and return best path
        scored_paths.sort(key=lambda x: x[0])
        return [scored_paths[0][1]] if scored_paths else []
