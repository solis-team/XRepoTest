"""
Ruby-specific CFG builder.
"""

from typing import Optional
from tree_sitter import Node

from xrepotest.lsp.cfg.builder import CFGBuilder
from xrepotest.lsp.cfg.types import CFGNode, CFGNodeType


class RubyCFGBuilder(CFGBuilder):
    """Ruby-specific CFG builder"""
    
    def process_node(self, node: Node, current: CFGNode) -> Optional[CFGNode]:
        """Process Ruby-specific AST nodes"""
        node_type = node.type
        
        # Function/class/module - process children sequentially
        if node_type in ['method', 'program', 'body_statement', 'then', 'do_block']:
            return self.process_block(node, current)
        
        # Function parameters
        elif node_type == 'method_parameters':
            return self.process_function_argument(node, current)
        
        # If statement
        elif node_type == 'if':
            return self._process_ruby_if_statement(node, current)
        
        # Unless (inverted if)
        elif node_type == 'unless':
            return self._process_ruby_unless_statement(node, current)
        
        # While loop
        elif node_type == 'while':
            return self.process_while_statement(node, current, 'body')
        
        # Until loop (inverted while)
        elif node_type == 'until':
            return self._process_ruby_until_loop(node, current)
        
        # For loop
        elif node_type == 'for':
            return self.process_for_statement(node, current, 'body')
        
        # Control flow
        elif node_type == 'next':
            return self.process_continue_statement(node, current)
        
        elif node_type == 'break':
            return self.process_break_statement(node, current)
        
        elif node_type == 'return':
            return self.process_return_statement(node, current)
        
        # Expression/assignment
        elif node_type in ['call', 'assignment', 'operator_assignment', 
                          'identifier', 'constant']:
            return self.process_expression_statement(node, current)
        
        # Unhandled node types - just continue
        else:
            return current
    
    def _process_ruby_if_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process Ruby if statement with elsif support"""
        # Create condition node
        condition_node = self.create_node(CFGNodeType.CONDITION, node)
        condition_node.condition = self.get_condition_text(node)
        self._check_condition_text(condition_node, node)
        self.connect(current, condition_node)
        
        # Create merge node
        merge_node = self.create_node(CFGNodeType.MERGED, node)
        
        # Process consequence (then branch)
        consequence = node.child_by_field_name('consequence')
        if consequence:
            consequence_node = self.create_node(CFGNodeType.BLOCK, consequence)
            condition_node.true_block = consequence_node
            self.connect(condition_node, consequence_node)
            self._process_block_and_connect_to_merge(consequence_node, merge_node)
        
        # Process alternative (elsif/else)
        alternative = node.child_by_field_name('alternative')
        if alternative:
            else_node = self.create_node(CFGNodeType.BLOCK, alternative)
            condition_node.false_block = else_node
            self.connect(condition_node, else_node)
            self._process_block_and_connect_to_merge(else_node, merge_node)
        else:
            # No else branch
            condition_node.false_block = merge_node
            self.connect(condition_node, merge_node)
        
        return merge_node
    
    def _process_ruby_unless_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process Ruby unless statement (inverted if)"""
        # Create condition node with negated condition
        condition_node = self.create_node(CFGNodeType.CONDITION, node)
        original_condition = self.get_condition_text(node)
        condition_node.condition = f"!({original_condition})" if original_condition else "true"
        self._check_condition_text(condition_node, node)
        self.connect(current, condition_node)
        
        # Create merge node
        merge_node = self.create_node(CFGNodeType.MERGED, node)
        
        # In unless, the "consequence" runs when condition is FALSE
        consequence = node.child_by_field_name('consequence')
        if consequence:
            consequence_node = self.create_node(CFGNodeType.BLOCK, consequence)
            condition_node.false_block = consequence_node  # Note: false_block!
            self.connect(condition_node, consequence_node)
            self._process_block_and_connect_to_merge(consequence_node, merge_node)
        
        # True path goes directly to merge
        condition_node.true_block = merge_node
        self.connect(condition_node, merge_node)
        
        return merge_node
    
    def _process_ruby_until_loop(self, node: Node, current: CFGNode) -> CFGNode:
        """Process Ruby until loop (inverted while)"""
        # Extract condition text and negate it
        condition_text = self.get_condition_text(node)
        negated_condition = f"!({condition_text})" if condition_text else "true"
        
        # Create condition node
        condition_node = self.create_node(CFGNodeType.CONDITION, node)
        condition_node.condition = negated_condition
        self._check_condition_text(condition_node, node)
        self.connect(current, condition_node)
        
        # Rest is same as while loop
        loop_node = self.create_node(CFGNodeType.LOOP, node)
        exit_node = self.create_node(CFGNodeType.EXIT_MERGED, node)
        
        # Setup loop context
        previous_loop_node = self.current_loop_node
        from xrepotest.lsp.cfg.types import LoopContext
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
        body = node.child_by_field_name('body')
        last_node = loop_node
        
        if body:
            body_node = self.create_node(CFGNodeType.BLOCK, body)
            self.connect(loop_node, body_node)
            
            last_node = body_node
            for child in body.children:
                processed = self.process_node(child, last_node)
                if processed:
                    last_node = processed
        
        # Finalize loop
        self.finalize_loop(loop_node, last_node, exit_node)
        self.current_loop_node = previous_loop_node
        
        return exit_node
