"""
Base CFG builder class with core control flow logic.

Ported from LSPRAG TypeScript implementation (src/cfg/builder.ts).
"""

import uuid
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict
from tree_sitter import Node, Parser

from xrepotest.lsp.cfg.types import CFGNode, CFGNodeType, ControlFlowGraph, LoopContext
from xrepotest.lsp.cfg.language_agnostic import LoopHeaderExtractor, LoopHeaderExtractorFactory

logger = logging.getLogger(__name__)


def _prune_text(text: str) -> str:
    """Prune multi-line text to first line + ellipsis"""
    if '\n' in text:
        return text.split('\n')[0] + ' ...'
    return text


class CFGBuilder(ABC):
    """Base CFG builder - abstract class for language-specific implementations"""
    
    def __init__(self, language: str, parser: Parser):
        self.language = language
        self.parser = parser
        self.nodes: Dict[str, CFGNode] = {}
        self.function_info: Dict[str, str] = {}
        self.current_loop_node: Optional[LoopContext] = None
        self.loop_header_extractor: LoopHeaderExtractor = \
            LoopHeaderExtractorFactory.create_extractor(language)
    
    def build_from_code(self, source_code: str) -> ControlFlowGraph:
        """Main entry point - parse code and build CFG"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        entry = self.create_node(CFGNodeType.ENTRY, tree.root_node)
        exit_node = self.create_node(CFGNodeType.EXIT, tree.root_node)
        
        last_node = self.process_node(tree.root_node, entry)
        if last_node:
            self.connect(last_node, exit_node)
        
        return ControlFlowGraph(
            entry=entry,
            exit=exit_node,
            nodes=self.nodes,
            language=self.language
        )
    
    def create_node(self, node_type: CFGNodeType, ast_node: Node) -> CFGNode:
        """Create a new CFG node"""
        text = ast_node.text.decode('utf8') if isinstance(ast_node.text, bytes) else ast_node.text
        
        node = CFGNode(
            id=uuid.uuid4().hex,
            text=_prune_text(text),
            type=node_type,
            ast_node=ast_node,
            successors=[],
            predecessors=[]
        )
        
        self.nodes[node.id] = node
        return node
    
    def connect(self, from_node: CFGNode, to_node: CFGNode):
        """Connect two CFG nodes"""
        if to_node not in from_node.successors:
            from_node.successors.append(to_node)
        if from_node not in to_node.predecessors:
            to_node.predecessors.append(from_node)
    
    def process_block(self, node: Node, current: CFGNode) -> CFGNode:
        """Process a block of statements sequentially"""
        last_node = current
        for child in node.children:
            processed = self.process_node(child, last_node)
            if processed:
                last_node = processed
        return last_node
    
    def process_function_argument(self, node: Node, current: CFGNode) -> CFGNode:
        """Process function parameters (stores in function_info)"""
        text = node.text.decode('utf8') if isinstance(node.text, bytes) else node.text
        self.function_info['signature'] = text
        return current
    
    def process_expression_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process a simple expression statement"""
        statement_node = self.create_node(CFGNodeType.STATEMENT, node)
        self.connect(current, statement_node)
        return statement_node
    
    def process_return_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process a return statement"""
        return_node = self.create_node(CFGNodeType.RETURN, node)
        self.connect(current, return_node)
        return return_node
    
    def process_break_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process a break statement"""
        if self.current_loop_node:
            break_node = self.create_node(CFGNodeType.BREAK, node)
            break_node.is_loop_break = True
            self.connect(current, break_node)
            self.current_loop_node.break_nodes.append(break_node)
            return break_node
        return current
    
    def process_continue_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process a continue statement"""
        if self.current_loop_node:
            continue_node = self.create_node(CFGNodeType.CONTINUE, node)
            continue_node.is_loop_continue = True
            continue_node.is_loop_back_edge = True
            self.connect(current, continue_node)
            self.current_loop_node.continue_nodes.append(continue_node)
            return continue_node
        return current
    
    def process_if_statement(self, node: Node, current: CFGNode,
                            consequence_field: str, else_clause_type: str) -> CFGNode:
        """Process an if statement with true/false branches"""
        # Create condition node
        condition_node = self.create_node(CFGNodeType.CONDITION, node)
        condition_node.condition = self.get_condition_text(node)
        self._check_condition_text(condition_node, node)
        self.connect(current, condition_node)
        
        # Create merge node for post-if continuation
        merge_node = self.create_node(CFGNodeType.MERGED, node)
        
        # Process consequence (then branch)
        consequence = node.child_by_field_name(consequence_field)
        if consequence:
            consequence_node = self.create_node(CFGNodeType.BLOCK, consequence)
            condition_node.true_block = consequence_node
            self.connect(condition_node, consequence_node)
            self._process_block_and_connect_to_merge(consequence_node, merge_node)
        
        # Process else branch
        else_clause = next((c for c in node.children if c.type == else_clause_type), None)
        if else_clause:
            else_node = self.create_node(CFGNodeType.BLOCK, else_clause)
            condition_node.false_block = else_node
            self.connect(condition_node, else_node)
            self._process_block_and_connect_to_merge(else_node, merge_node)
        else:
            # No else branch - condition false goes directly to merge
            condition_node.false_block = merge_node
            self.connect(condition_node, merge_node)
        
        return merge_node
    
    def process_for_statement(self, node: Node, current: CFGNode, body_type: str) -> CFGNode:
        """Process a for loop"""
        # Extract loop header
        loop_header = self.loop_header_extractor.extract_loop_header(node)
        
        # Create nodes
        loop_node = self.create_node(CFGNodeType.LOOP, node)
        for_statement_node = self.create_node(CFGNodeType.STATEMENT, node)
        for_statement_node.text = loop_header  # Override with just the header
        
        self.connect(current, for_statement_node)
        self.connect(for_statement_node, loop_node)
        
        # Setup loop context
        previous_loop_node = self.current_loop_node
        exit_node = self.create_node(CFGNodeType.EXIT_MERGED, node)
        self.current_loop_node = LoopContext(
            node=loop_node,
            break_nodes=[],
            continue_nodes=[],
            exit_merged_node=exit_node
        )
        
        # Process body
        body = node.child_by_field_name(body_type)
        last_node = loop_node
        
        if body:
            body_node = self.create_node(CFGNodeType.BLOCK, body)
            self.connect(loop_node, body_node)
            
            last_node = body_node
            for child in body.children:
                processed = self.process_node(child, last_node)
                if processed:
                    last_node = processed
        
        # Finalize loop connections
        self.finalize_loop(self.current_loop_node, last_node, loop_node)
        self.current_loop_node = previous_loop_node
        
        return exit_node
    
    def process_while_statement(self, node: Node, current: CFGNode, body_type: str) -> CFGNode:
        """Process a while loop"""
        # Create condition node
        condition_node = self.create_node(CFGNodeType.CONDITION, node)
        condition_node.condition = self.get_condition_text(node)
        self._check_condition_text(condition_node, node)
        self.connect(current, condition_node)
        
        # Create loop and exit nodes
        loop_node = self.create_node(CFGNodeType.LOOP, node)
        exit_node = self.create_node(CFGNodeType.EXIT_MERGED, node)
        
        # Setup loop context
        previous_loop_node = self.current_loop_node
        self.current_loop_node = LoopContext(
            node=loop_node,
            break_nodes=[],
            continue_nodes=[],
            exit_merged_node=exit_node
        )
        
        # Condition true -> loop body
        condition_node.true_block = loop_node
        self.connect(condition_node, loop_node)
        
        # Condition false -> exit
        condition_node.false_block = exit_node
        self.connect(condition_node, exit_node)
        
        # Process body
        body = node.child_by_field_name(body_type)
        last_node = loop_node
        
        if body:
            body_node = self.create_node(CFGNodeType.BLOCK, body)
            self.connect(loop_node, body_node)
            
            last_node = body_node
            for child in body.children:
                processed = self.process_node(child, last_node)
                if processed:
                    last_node = processed
        
        # Finalize loop (back edge to condition, not loop node)
        self.finalize_loop(self.current_loop_node, last_node, condition_node)
        self.current_loop_node = previous_loop_node
        
        return exit_node
    
    def finalize_loop(self, loop_context: LoopContext, last_node: CFGNode, loop_start_node: CFGNode):
        """Connect break/continue nodes and create back edge"""
        # Back edge: last statement in loop goes back to loop start
        self.connect(last_node, loop_start_node)
        
        # Continue nodes go back to loop start
        for continue_node in loop_context.continue_nodes:
            self.connect(continue_node, loop_start_node)
        
        # Break nodes go to exit
        if loop_context.exit_merged_node:
            for break_node in loop_context.break_nodes:
                self.connect(break_node, loop_context.exit_merged_node)
    
    def get_condition_text(self, node: Node) -> str:
        """Extract condition text from node - language-specific override may be needed"""
        condition_child = node.child_by_field_name('condition')
        if condition_child:
            text = condition_child.text.decode('utf8') if isinstance(condition_child.text, bytes) else condition_child.text
            return text
        return ""
    
    def _check_condition_text(self, condition_node: CFGNode, node: Node):
        """Warn if condition text is empty"""
        if not condition_node.condition:
            logger.warning(f"Condition node has empty condition text. Node type: {node.type}")
    
    def _process_block_and_connect_to_merge(self, block_node: CFGNode, merge_node: CFGNode):
        """Process all children in a block and connect final node to merge"""
        last_node = block_node
        for child in block_node.ast_node.children:
            processed = self.process_node(child, last_node)
            if processed:
                last_node = processed
        
        if last_node != block_node:
            self.connect(last_node, merge_node)
    
    @abstractmethod
    def process_node(self, node: Node, current: CFGNode) -> Optional[CFGNode]:
        """Process a node - must be implemented by language-specific subclass"""
        pass
