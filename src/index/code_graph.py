"""Code graph builder using AST analysis."""

import ast
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
import networkx as nx

from ..agent.schemas import UsageLocation


class CodeGraphBuilder:
    """Builds call graph and usage graph from Python code."""
    
    def __init__(self, repo_path: str):
        """Initialize with repository path."""
        self.repo_path = Path(repo_path)
        self.graph = nx.DiGraph()
        self.symbol_definitions: Dict[str, str] = {}  # symbol -> file
        self.symbol_usages: Dict[str, List[UsageLocation]] = {}  # symbol -> [locations]
    
    def analyze_file(self, file_path: Path) -> Dict[str, any]:
        """Analyze a single Python file with AST.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            Dict with defined symbols, imports, and calls
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                source = f.read()
        except Exception:
            return {'defines': [], 'imports': [], 'calls': []}
        
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return {'defines': [], 'imports': [], 'calls': []}
        
        analyzer = FileAnalyzer(file_path, source)
        analyzer.visit(tree)
        
        return {
            'defines': analyzer.defined_symbols,
            'imports': analyzer.imports,
            'calls': analyzer.function_calls,
            'usages': analyzer.usages
        }
    
    def build_graph(self, include_tests: bool = True) -> nx.DiGraph:
        """Build complete code graph for repository.
        
        Args:
            include_tests: Whether to include test files
            
        Returns:
            NetworkX directed graph
        """
        # Find all Python files
        python_files = list(self.repo_path.rglob('*.py'))
        
        if not include_tests:
            python_files = [
                f for f in python_files
                if 'test' not in f.name.lower() and 'tests' not in str(f).lower()
            ]
        
        # Analyze each file
        for file_path in python_files:
            rel_path = str(file_path.relative_to(self.repo_path))
            
            analysis = self.analyze_file(file_path)
            
            # Add nodes for defined symbols
            for symbol in analysis['defines']:
                full_name = f"{rel_path}::{symbol}"
                self.graph.add_node(
                    full_name,
                    type='symbol',
                    file=rel_path,
                    name=symbol
                )
                self.symbol_definitions[symbol] = rel_path
            
            # Add edges for function calls
            for call in analysis['calls']:
                caller = f"{rel_path}::current_scope"
                self.graph.add_edge(caller, call, type='calls')
            
            # Store usages
            for usage in analysis['usages']:
                symbol = usage.get('symbol')
                if symbol:
                    if symbol not in self.symbol_usages:
                        self.symbol_usages[symbol] = []
                    
                    self.symbol_usages[symbol].append(UsageLocation(
                        file_path=rel_path,
                        line_number=usage['line'],
                        context=usage['context'],
                        is_test='test' in rel_path.lower()
                    ))
        
        return self.graph
    
    def find_usages(self, symbol_name: str) -> List[UsageLocation]:
        """Find all usages of a symbol.
        
        Args:
            symbol_name: Name of function/class/variable
            
        Returns:
            List of UsageLocation objects
        """
        return self.symbol_usages.get(symbol_name, [])
    
    def find_callers(self, symbol_name: str) -> List[str]:
        """Find all symbols that call this symbol.
        
        Args:
            symbol_name: Name of function/class
            
        Returns:
            List of caller symbol names
        """
        callers = []
        
        for node in self.graph.nodes():
            if self.graph.has_edge(node, symbol_name):
                callers.append(node)
        
        return callers
    
    def find_dependencies(self, file_path: str, depth: int = 2) -> Set[str]:
        """Find files that depend on the given file.
        
        Args:
            file_path: Path to file
            depth: How many hops to traverse
            
        Returns:
            Set of dependent file paths
        """
        dependencies = set()
        
        # Find symbols defined in this file
        file_symbols = [
            node for node in self.graph.nodes()
            if self.graph.nodes[node].get('file') == file_path
        ]
        
        # Find usages of these symbols
        for symbol in file_symbols:
            usages = self.find_usages(self.graph.nodes[symbol]['name'])
            for usage in usages:
                dependencies.add(usage.file_path)
        
        return dependencies
    
    def get_symbol_centrality(self) -> Dict[str, float]:
        """Calculate betweenness centrality for symbols.
        
        Returns:
            Dict mapping symbol names to centrality scores
        """
        try:
            return nx.betweenness_centrality(self.graph)
        except:
            return {}


class FileAnalyzer(ast.NodeVisitor):
    """AST visitor to extract symbols, calls, and usages."""
    
    def __init__(self, file_path: Path, source: str):
        self.file_path = file_path
        self.source_lines = source.split('\n')
        self.defined_symbols: List[str] = []
        self.imports: List[str] = []
        self.function_calls: List[str] = []
        self.usages: List[Dict] = []
        self.current_class: Optional[str] = None
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definition."""
        if self.current_class:
            symbol = f"{self.current_class}.{node.name}"
        else:
            symbol = node.name
        
        self.defined_symbols.append(symbol)
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Visit async function definition."""
        self.visit_FunctionDef(node)
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definition."""
        self.defined_symbols.append(node.name)
        
        # Track current class for methods
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class
    
    def visit_Import(self, node: ast.Import):
        """Visit import statement."""
        for alias in node.names:
            self.imports.append(alias.name)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Visit from...import statement."""
        if node.module:
            for alias in node.names:
                self.imports.append(f"{node.module}.{alias.name}")
    
    def visit_Call(self, node: ast.Call):
        """Visit function call."""
        # Extract function name
        func_name = None
        
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        
        if func_name:
            self.function_calls.append(func_name)
            
            # Record usage with context
            line_num = node.lineno
            context = self._get_context(line_num)
            
            self.usages.append({
                'symbol': func_name,
                'line': line_num,
                'context': context,
                'type': 'call'
            })
        
        self.generic_visit(node)
    
    def visit_Name(self, node: ast.Name):
        """Visit name reference (variable usage)."""
        if isinstance(node.ctx, ast.Load):  # Variable is being read
            line_num = node.lineno
            context = self._get_context(line_num)
            
            self.usages.append({
                'symbol': node.id,
                'line': line_num,
                'context': context,
                'type': 'reference'
            })
        
        self.generic_visit(node)
    
    def _get_context(self, line_num: int, context_lines: int = 2) -> str:
        """Get source code context around a line.
        
        Args:
            line_num: Line number (1-indexed)
            context_lines: Lines of context before/after
            
        Returns:
            Context string
        """
        start = max(0, line_num - context_lines - 1)
        end = min(len(self.source_lines), line_num + context_lines)
        
        return '\n'.join(self.source_lines[start:end])
