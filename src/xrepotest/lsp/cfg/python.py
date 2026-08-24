"""
Python-specific CFG builder.

Ported from LSPRAG TypeScript implementation (src/cfg/python.ts).
"""

from typing import Optional
from tree_sitter import Node

from xrepotest.lsp.cfg.builder import CFGBuilder
from xrepotest.lsp.cfg.types import CFGNode, CFGNodeType


class PythonCFGBuilder(CFGBuilder):
    """Python-specific CFG builder"""
    
    def process_node(self, node: Node, current: CFGNode) -> Optional[CFGNode]:
        """Process Python-specific AST nodes"""
        node_type = node.type
        
        # Function/module/block - process children sequentially
        if node_type in ['function_definition', 'module', 'block']:
            return self.process_block(node, current)
        
        # Function parameters
        elif node_type == 'parameters':
            return self.process_function_argument(node, current)
        
        # If statement (may have elif)
        elif node_type == 'if_statement':
            return self._process_python_if_statement(node, current)
        
        # While loop
        elif node_type == 'while_statement':
            return self.process_while_statement(node, current, 'block')
        
        # For loop
        elif node_type == 'for_statement':
            return self.process_for_statement(node, current, 'body')
        
        # Control flow
        elif node_type == 'continue_statement':
            return self.process_continue_statement(node, current)
        
        elif node_type == 'break_statement':
            return self.process_break_statement(node, current)
        
        elif node_type == 'return_statement':
            return self.process_return_statement(node, current)
        
        # Expression statement
        elif node_type == 'expression_statement':
            return self.process_expression_statement(node, current)
        
        # Try/except
        elif node_type == 'try_statement':
            return self._process_python_try_statement(node, current)
        
        # Unhandled node types - just continue
        else:
            return current
    
    def _process_python_if_statement(self, node: Node, current: CFGNode,
                                     consequence_field: str = 'consequence',
                                     else_clause_type: str = 'else_clause') -> CFGNode:
        """Process Python if statement with elif support"""
        # Create condition node
        condition_node = self.create_node(CFGNodeType.CONDITION, node)
        current_condition_node = condition_node
        condition_node.condition = self.get_condition_text(node)
        self._check_condition_text(condition_node, node)
        self.connect(current, condition_node)
        
        # Create merge node
        merge_node = self.create_node(CFGNodeType.MERGED, node)
        
        # Process consequence (then branch)
        consequence = node.child_by_field_name(consequence_field)
        if consequence:
            consequence_node = self.create_node(CFGNodeType.BLOCK, consequence)
            condition_node.true_block = consequence_node
            self.connect(condition_node, consequence_node)
            self._process_block_and_connect_to_merge(consequence_node, merge_node)
        
        # Process elif clauses (Python-specific)
        elif_nodes = [c for c in node.children if c.type == 'elif_clause']
        for elif_node in elif_nodes:
            elif_condition_node = self.create_node(CFGNodeType.CONDITION, elif_node)
            elif_condition_node.condition = self._get_python_condition_text(elif_node)
            self._check_condition_text(elif_condition_node, elif_node)
            
            # Chain: previous condition's false -> this elif condition
            self.connect(current_condition_node, elif_condition_node)
            current_condition_node.false_block = elif_condition_node
            current_condition_node = elif_condition_node
            
            # Process elif body
            elif_body = elif_node.child_by_field_name(consequence_field)
            if elif_body:
                elif_body_node = self.create_node(CFGNodeType.BLOCK, elif_body)
                elif_condition_node.true_block = elif_body_node
                self.connect(elif_condition_node, elif_body_node)
                self._process_block_and_connect_to_merge(elif_body_node, merge_node)
        
        # Process else clause
        else_clause = next((c for c in node.children if c.type == else_clause_type), None)
        if else_clause:
            else_node = self.create_node(CFGNodeType.BLOCK, else_clause)
            current_condition_node.false_block = else_node
            self.connect(current_condition_node, else_node)
            self._process_block_and_connect_to_merge(else_node, merge_node)
        else:
            # No else - last condition false goes to merge
            current_condition_node.false_block = merge_node
            self.connect(current_condition_node, merge_node)
        
        return merge_node
    
    def _process_python_try_statement(self, node: Node, current: CFGNode) -> CFGNode:
        """Process Python try/except/finally statement"""
        # Create try node
        try_node = self.create_node(CFGNodeType.TRY, node)
        self.connect(current, try_node)
        
        # Create merge node
        merge_node = self.create_node(CFGNodeType.MERGED, node)
        
        # Process try body
        try_body = node.child_by_field_name('block')
        last_try_node = try_node
        if try_body:
            body_node = self.create_node(CFGNodeType.BLOCK, try_body)
            self.connect(try_node, body_node)
            last_try_node = body_node
            for child in try_body.children:
                processed = self.process_node(child, last_try_node)
                if processed:
                    last_try_node = processed
        
        self.connect(last_try_node, merge_node)
        
        # Process except clauses
        except_clauses = [c for c in node.children if c.type == 'except_clause']
        for except_clause in except_clauses:
            except_node = self.create_node(CFGNodeType.CATCH, except_clause)
            self.connect(try_node, except_node)
            
            # Process except body
            except_body = except_clause.child_by_field_name('block')
            last_except_node = except_node
            if except_body:
                for child in except_body.children:
                    processed = self.process_node(child, last_except_node)
                    if processed:
                        last_except_node = processed
            
            self.connect(last_except_node, merge_node)
        
        # Process finally clause
        finally_clause = node.child_by_field_name('finally_clause')
        if finally_clause:
            finally_node = self.create_node(CFGNodeType.FINALLY, finally_clause)
            self.connect(merge_node, finally_node)
            
            # Process finally body
            finally_body = finally_clause.child_by_field_name('block')
            last_finally_node = finally_node
            if finally_body:
                for child in finally_body.children:
                    processed = self.process_node(child, last_finally_node)
                    if processed:
                        last_finally_node = processed
            
            return last_finally_node
        
        return merge_node
    
    def _get_python_condition_text(self, node: Node) -> str:
        """Extract condition text from Python if/elif/while statements"""
        # Try to find condition child first
        condition_child = node.child_by_field_name('condition')
        if condition_child:
            text = condition_child.text.decode('utf8') if isinstance(condition_child.text, bytes) else condition_child.text
            return text
        
        # Search children for condition-like nodes
        for child in node.children:
            if child.type in ['comparison_operator', 'boolean_operator', 'identifier', 
                             'call', 'not_operator', 'binary_operator']:
                text = child.text.decode('utf8') if isinstance(child.text, bytes) else child.text
                return text
        
        return ""
    
    def get_condition_text(self, node: Node) -> str:
        """Override to handle Python-specific condition extraction"""
        return self._get_python_condition_text(node)
