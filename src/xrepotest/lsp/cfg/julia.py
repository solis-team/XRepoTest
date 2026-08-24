"""
Julia-specific CFG builder.
"""

from typing import Optional
from tree_sitter import Node

from xrepotest.lsp.cfg.builder import CFGBuilder
from xrepotest.lsp.cfg.types import CFGNode, CFGNodeType, LoopContext


class JuliaCFGBuilder(CFGBuilder):
    """Julia-specific CFG builder"""
    
    def process_node(self, node: Node, current: CFGNode) -> Optional[CFGNode]:
        """Process Julia-specific AST nodes"""
        node_type = node.type
        
        # Function/module - process children sequentially
        if node_type in ['function_definition', 'module_definition', 'source_file',
                         'compound_statement', 'block']:
            return self.process_block(node, current)
        
        # Function parameters
        elif node_type in ['parameter_list', 'typed_parameter']:
            return self.process_function_argument(node, current)
        
        # If statement
        elif node_type == 'if_statement':
            return self._process_julia_if_statement(node, current)
        
        # While loop
        elif node_type == 'while_statement':
            return self.process_while_statement(node, current, 'body')
        
        # For loop
        elif node_type == 'for_statement':
            return self._process_julia_for_statement(node, current)
        
        # Control flow
        elif node_type == 'continue_statement':
            return self.process_continue_statement(node, current)
        
        elif node_type == 'break_statement':
            return self.process_break_statement(node, current)
        
        elif node_type == 'return_statement':
            return self.process_return_statement(node, current)
        
        # Binary expression with || or && - treat as implicit condition
        elif node_type == 'binary_expression':
            return self._process_julia_binary_expression(node, current)
        
        # Expression/assignment
        elif node_type in ['assignment', 'call_expression',
                          'identifier', 'operator_assignment']:
            return self.process_expression_statement(node, current)
        
        # Unhandled node types - just continue
        else:
            return current
    
    def _process_julia_if_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process Julia if statement with elseif support"""
        # Create condition node
        condition_node = self.create_node(CFGNodeType.CONDITION, node)
        condition_node.condition = self.get_condition_text(node)
        self._check_condition_text(condition_node, node)
        self.connect(current, condition_node)
        
        # Create merge node
        merge_node = self.create_node(CFGNodeType.MERGED, node)
        
        # Find then clause
        consequence = None
        alternative = None
        for child in node.children:
            if child.type == 'compound_statement' and not consequence:
                consequence = child
            elif child.type in ['elseif_clause', 'else_clause', 'if_statement']:
                alternative = child
                break
        
        # Process consequence (then branch)
        if consequence:
            consequence_node = self.create_node(CFGNodeType.BLOCK, consequence)
            condition_node.true_block = consequence_node
            self.connect(condition_node, consequence_node)
            self._process_block_and_connect_to_merge(consequence_node, merge_node)
        
        # Process alternative (elseif/else)
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

    def _process_julia_binary_expression(self, node: Node, current: CFGNode) -> CFGNode:
        """Process Julia binary expressions with || or && as implicit conditions"""
        # Find the operator by checking children for 'operator' type nodes
        operator_text = None
        for child in node.children:
            if child.type == 'operator':
                operator_text = child.text.decode('utf8') if isinstance(child.text, bytes) else child.text
                break
        
        # If it's a || or && expression, treat it as a condition
        if operator_text in ['||', '&&', '<', '>', '<=', '>=', '==', '!=']:
            condition_node = self.create_node(CFGNodeType.CONDITION, node)
            # Get the full expression text as the condition
            condition_text = node.text.decode('utf8') if isinstance(node.text, bytes) else node.text
            condition_node.condition = condition_text
            self.connect(current, condition_node)
            
            # Create merge node for short-circuit evaluation
            # Both branches continue to the same next statement
            merge_node = self.create_node(CFGNodeType.MERGED, node)
            
            # For short-circuit evaluation, both paths lead to merge
            # True path: condition is satisfied, continue
            # False path: right side is evaluated (e.g., throw), but still merges
            condition_node.true_block = merge_node
            condition_node.false_block = merge_node
            self.connect(condition_node, merge_node)
            
            return merge_node
        
        # Otherwise, treat as regular expression
        return self.process_expression_statement(node, current)

    def _process_julia_for_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process Julia for loop - handles Julia's direct child structure"""
        # Extract loop header
        loop_header = self.loop_header_extractor.extract_loop_header(node)
        
        # Create nodes
        loop_node = self.create_node(CFGNodeType.LOOP, node)
        for_statement_node = self.create_node(CFGNodeType.STATEMENT, node)
        for_statement_node.text = loop_header
        
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
        
        # For loops also exit normally (when iteration completes)
        # Connect loop node to exit for path traversal
        self.connect(loop_node, exit_node)
        
        # Process body - Julia has statements as direct children after for_binding
        last_node = loop_node
        found_binding = False
        
        for child in node.children:
            # Skip 'for' keyword and for_binding
            if child.type in ['for', 'for_binding']:
                found_binding = True
                continue
            # Skip 'end' keyword
            if child.type == 'end':
                break
            # Process actual body statements
            if found_binding:
                processed = self.process_node(child, last_node)
                if processed:
                    last_node = processed
        
        # Finalize loop connections
        self.finalize_loop(self.current_loop_node, last_node, loop_node)
        self.current_loop_node = previous_loop_node
        
        return exit_node
