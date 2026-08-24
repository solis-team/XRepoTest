"""
PHP-specific CFG builder.
"""

from typing import Optional
from tree_sitter import Node

from xrepotest.lsp.cfg.builder import CFGBuilder
from xrepotest.lsp.cfg.types import CFGNode, CFGNodeType


class PHPCFGBuilder(CFGBuilder):
    """PHP-specific CFG builder"""
    
    def process_node(self, node: Node, current: CFGNode) -> Optional[CFGNode]:
        """Process PHP-specific AST nodes"""
        node_type = node.type
        
        # Function/class - process children sequentially
        if node_type in ['function_definition', 'method_declaration', 'program', 
                         'compound_statement']:
            return self.process_block(node, current)
        
        # Function parameters
        elif node_type == 'formal_parameters':
            return self.process_function_argument(node, current)
        
        # If statement
        elif node_type == 'if_statement':
            return self._process_php_if_statement(node, current)
        
        # While loop
        elif node_type == 'while_statement':
            return self.process_while_statement(node, current, 'body')
        
        # For loop
        elif node_type == 'for_statement':
            return self.process_for_statement(node, current, 'body')
        
        # Foreach loop
        elif node_type == 'foreach_statement':
            return self.process_for_statement(node, current, 'body')
        
        # Do-while loop
        elif node_type == 'do_statement':
            return self._process_php_do_while(node, current)
        
        # Control flow
        elif node_type == 'continue_statement':
            return self.process_continue_statement(node, current)
        
        elif node_type == 'break_statement':
            return self.process_break_statement(node, current)
        
        elif node_type == 'return_statement':
            return self.process_return_statement(node, current)
        
        # Expression/assignment
        elif node_type in ['expression_statement', 'assignment_expression',
                          'augmented_assignment_expression']:
            return self.process_expression_statement(node, current)
        
        # Braces (skip)
        elif node_type in ['{', '}']:
            return current
        
        # Unhandled node types - just continue
        else:
            return current
    
    def _process_php_if_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process PHP if statement with elseif support"""
        # Create condition node
        condition_node = self.create_node(CFGNodeType.CONDITION, node)
        condition_node.condition = self.get_condition_text(node)
        self._check_condition_text(condition_node, node)
        self.connect(current, condition_node)
        
        # Create merge node
        merge_node = self.create_node(CFGNodeType.MERGED, node)
        
        # Process body (then branch)
        body = node.child_by_field_name('body')
        if body:
            consequence_node = self.create_node(CFGNodeType.BLOCK, body)
            condition_node.true_block = consequence_node
            self.connect(condition_node, consequence_node)
            self._process_block_and_connect_to_merge(consequence_node, merge_node)
        
        # Process alternative (elseif/else)
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
    
    def _process_php_do_while(self, node: Node, current: CFGNode) -> CFGNode:
        """Process PHP do-while loop (body executes at least once)"""
        # Create loop node
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
        
        # Connect entry to loop (body executes first)
        self.connect(current, loop_node)
        
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
        
        # After body, check condition
        condition_text = self.get_condition_text(node)
        if condition_text:
            condition_node = self.create_node(CFGNodeType.CONDITION, node)
            condition_node.condition = condition_text
            self._check_condition_text(condition_node, node)
            self.connect(last_node, condition_node)
            
            # True -> back to loop, False -> exit
            condition_node.true_block = loop_node
            self.connect(condition_node, loop_node)
            condition_node.false_block = exit_node
            self.connect(condition_node, exit_node)
        else:
            # No condition, loop back
            self.connect(last_node, loop_node)
        
        # Finalize loop
        self.finalize_loop(loop_node, last_node, exit_node)
        self.current_loop_node = previous_loop_node
        
        return exit_node
