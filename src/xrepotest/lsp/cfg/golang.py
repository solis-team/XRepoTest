"""
Go-specific CFG builder.

Ported from LSPRAG TypeScript implementation (src/cfg/golang.ts).
"""

from typing import Optional
from tree_sitter import Node

from xrepotest.lsp.cfg.builder import CFGBuilder
from xrepotest.lsp.cfg.types import CFGNode, CFGNodeType


class GolangCFGBuilder(CFGBuilder):
    """Go-specific CFG builder"""
    
    def process_node(self, node: Node, current: CFGNode) -> Optional[CFGNode]:
        """Process Go-specific AST nodes"""
        node_type = node.type
        
        # Function/source file - process children sequentially
        if node_type in ['func', 'function_declaration', 'method_declaration', 
                         'source_file', 'block', 'statement_list']:
            return self.process_block(node, current)
        
        # Function parameters
        elif node_type == 'parameter_list':
            return self.process_function_argument(node, current)
        
        # If statement
        elif node_type == 'if_statement':
            return self._process_go_if_statement(node, current)
        
        # For loop (Go uses 'for' for all loops)
        elif node_type == 'for_statement':
            return self._process_go_for_statement(node, current)
        
        # Control flow
        elif node_type == 'continue_statement':
            return self.process_continue_statement(node, current)
        
        elif node_type == 'break_statement':
            return self.process_break_statement(node, current)
        
        elif node_type == 'return_statement':
            return self.process_return_statement(node, current)
        
        # Braces (skip)
        elif node_type in ['{', '}']:
            return current
        
        # Statements
        elif node_type in ['identifier', 'type_identifier', 'expression_statement',
                          'short_var_declaration', 'assignment_statement',
                          'inc_statement', 'dec_statement']:
            return self.process_expression_statement(node, current)
        
        # Unhandled node types - just continue
        else:
            return current
    
    def _process_go_if_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process Go if statement (uses named fields instead of child types)"""
        # Create condition node
        condition_node = self.create_node(CFGNodeType.CONDITION, node)
        condition_node.condition = self.get_condition_text(node)
        self._check_condition_text(condition_node, node)
        self.connect(current, condition_node)
        
        # Create merge node for post-if continuation
        merge_node = self.create_node(CFGNodeType.MERGED, node)
        
        # Process consequence (then branch)
        consequence = node.child_by_field_name('consequence')
        if consequence:
            consequence_node = self.create_node(CFGNodeType.BLOCK, consequence)
            condition_node.true_block = consequence_node
            self.connect(condition_node, consequence_node)
            self._process_block_and_connect_to_merge(consequence_node, merge_node)
        
        # Process alternative (else branch) - use field, not child type
        alternative = node.child_by_field_name('alternative')
        if alternative:
            else_node = self.create_node(CFGNodeType.BLOCK, alternative)
            condition_node.false_block = else_node
            self.connect(condition_node, else_node)
            self._process_block_and_connect_to_merge(else_node, merge_node)
        else:
            # No else branch - condition false goes directly to merge
            condition_node.false_block = merge_node
            self.connect(condition_node, merge_node)
        
        return merge_node
    
    def _process_go_for_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process Go for statement (handles both condition-based and range-based loops)"""
        # Extract condition text
        condition_text = self._get_go_condition_text(node)
        loop_header = self.loop_header_extractor.extract_loop_header(node)
        
        # If has condition, create condition node first
        if condition_text:
            # Create condition node
            condition_node = self.create_node(CFGNodeType.CONDITION, node)
            condition_node.condition = condition_text
            self._check_condition_text(condition_node, node)
            self.connect(current, condition_node)
            
            # Create loop node
            loop_node = self.create_node(CFGNodeType.LOOP, node)
            for_statement_node = self.create_node(CFGNodeType.STATEMENT, node)
            for_statement_node.text = loop_header
            
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
            
            # Condition true -> loop
            condition_node.true_block = for_statement_node
            self.connect(condition_node, for_statement_node)
            self.connect(for_statement_node, loop_node)
            
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
            
            # Finalize loop (back edge to condition)
            self.finalize_loop(self.current_loop_node, last_node, condition_node)
            self.current_loop_node = previous_loop_node
            
            return exit_node
        else:
            # No condition (range-based or infinite loop)
            return self.process_for_statement(node, current, 'body')
    
    def _get_go_condition_text(self, node: Node) -> str:
        """Extract condition text from Go for/if statements"""
        # Try to find condition child first
        condition_child = node.child_by_field_name('condition')
        if condition_child:
            text = condition_child.text.decode('utf8') if isinstance(condition_child.text, bytes) else condition_child.text
            return text
        
        # Search children for condition-like nodes
        for child in node.children:
            if child.type in ['binary_expression', 'comparison_expression', 'selector_expression',
                             'identifier', 'unary_expression', 'call_expression']:
                text = child.text.decode('utf8') if isinstance(child.text, bytes) else child.text
                return text
            elif child.type == 'range_clause':
                # Range-based for loop - no condition
                return ""
        
        return ""
    
    def get_condition_text(self, node: Node) -> str:
        """Override to handle Go-specific condition extraction"""
        return self._get_go_condition_text(node)
