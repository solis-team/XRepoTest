"""
Rust-specific CFG builder.
"""

from typing import Optional
from tree_sitter import Node

from xrepotest.lsp.cfg.builder import CFGBuilder
from xrepotest.lsp.cfg.types import CFGNode, CFGNodeType


class RustCFGBuilder(CFGBuilder):
    """Rust-specific CFG builder"""
    
    def process_node(self, node: Node, current: CFGNode) -> Optional[CFGNode]:
        """Process Rust-specific AST nodes"""
        node_type = node.type
        
        # Function/block - process children sequentially
        if node_type in ['function_item', 'source_file', 'block', 'declaration_list',
                         'else_clause']:
            return self.process_block(node, current)
        
        # Function parameters
        elif node_type == 'parameters':
            return self.process_function_argument(node, current)
        
        # If expression
        elif node_type == 'if_expression':
            return self._process_rust_if_expression(node, current)
        
        # While loop
        elif node_type == 'while_expression':
            return self.process_while_statement(node, current, 'body')
        
        # For loop
        elif node_type == 'for_expression':
            return self.process_for_statement(node, current, 'body')
        
        # Loop (infinite loop)
        elif node_type == 'loop_expression':
            return self._process_rust_loop(node, current)
        
        # Control flow
        elif node_type == 'continue_expression':
            return self.process_continue_statement(node, current)
        
        elif node_type == 'break_expression':
            return self.process_break_statement(node, current)
        
        elif node_type == 'return_expression':
            return self.process_return_statement(node, current)
        
        # Expression statement
        elif node_type in ['expression_statement', 'let_declaration', 
                          'assignment_expression', 'compound_assignment_expr']:
            # Check if it's an expression_statement wrapping an if_expression
            if node_type == 'expression_statement' and node.children:
                first_child = node.children[0]
                if first_child.type == 'if_expression':
                    return self._process_rust_if_expression(first_child, current)
            return self.process_expression_statement(node, current)
        
        # Braces (skip)
        elif node_type in ['{', '}']:
            return current
        
        # Unhandled node types - just continue
        else:
            return current
    
    def _process_rust_if_expression(self, node: Node, current: CFGNode) -> CFGNode:
        """Process Rust if expression (uses named fields)"""
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
        
        # Process alternative (else/else if)
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
    
    def _process_rust_loop(self, node: Node, current: CFGNode) -> CFGNode:
        """Process Rust infinite loop: loop { ... }"""
        # Create loop node
        loop_node = self.create_node(CFGNodeType.LOOP, node)
        self.connect(current, loop_node)
        
        # Setup loop context
        exit_node = self.create_node(CFGNodeType.EXIT_MERGED, node)
        previous_loop_node = self.current_loop_node
        from xrepotest.lsp.cfg.types import LoopContext
        self.current_loop_node = LoopContext(
            node=loop_node,
            break_nodes=[],
            continue_nodes=[],
            exit_merged_node=exit_node
        )
        
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
