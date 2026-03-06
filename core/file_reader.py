"""
File reader and Python AST parser for code analysis.
"""
import os
import ast
from typing import List, Dict, Any, Optional
from pathlib import Path
from models.analysis import FileInfo


class FileReader:
    """Read and parse Python files for analysis."""
    
    def __init__(
        self,
        target_path: str,
        file_extensions: List[str] = [".py"],
        exclude_dirs: List[str] = None,
        max_file_size_kb: int = 500
    ):
        """
        Initialize file reader.
        
        Args:
            target_path: Path to analyze
            file_extensions: File extensions to include
            exclude_dirs: Directories to exclude
            max_file_size_kb: Maximum file size in KB
        """
        self.target_path = Path(target_path)
        self.file_extensions = file_extensions
        self.exclude_dirs = exclude_dirs or ["__pycache__", ".git", "venv", ".venv", "env"]
        self.max_file_size_kb = max_file_size_kb
    
    def find_files(self) -> List[Path]:
        """
        Find all Python files in target path.
        
        Returns:
            List of file paths
        """
        files = []
        
        for root, dirs, filenames in os.walk(self.target_path):
            # Exclude directories
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            for filename in filenames:
                if any(filename.endswith(ext) for ext in self.file_extensions):
                    file_path = Path(root) / filename
                    
                    # Check file size
                    size_kb = file_path.stat().st_size / 1024
                    if size_kb <= self.max_file_size_kb:
                        files.append(file_path)
        
        return files
    
    def read_file(self, file_path: Path) -> str:
        """
        Read file content.
        
        Args:
            file_path: Path to file
        
        Returns:
            File content as string
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            raise Exception(f"Failed to read {file_path}: {e}")
    
    def get_file_info(self, file_path: Path) -> FileInfo:
        """
        Get file metadata.
        
        Args:
            file_path: Path to file
        
        Returns:
            FileInfo object
        """
        content = self.read_file(file_path)
        
        # Parse AST to count functions and classes
        try:
            tree = ast.parse(content)
            functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        except:
            functions = []
            classes = []
        
        return FileInfo(
            path=str(file_path),
            name=file_path.name,
            size_bytes=file_path.stat().st_size,
            lines_of_code=len(content.splitlines()),
            functions_count=len(functions),
            classes_count=len(classes)
        )
    
    def parse_ast(self, code: str) -> Optional[ast.Module]:
        """
        Parse Python code to AST.
        
        Args:
            code: Python source code
        
        Returns:
            AST Module or None if parsing fails
        """
        try:
            return ast.parse(code)
        except SyntaxError as e:
            print(f"Syntax error parsing code: {e}")
            return None
    
    def extract_functions(self, tree: ast.Module) -> List[Dict[str, Any]]:
        """
        Extract function information from AST.
        
        Args:
            tree: AST Module
        
        Returns:
            List of function info dicts
        """
        functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_info = {
                    "name": node.name,
                    "line": node.lineno,
                    "parameters": [arg.arg for arg in node.args.args],
                    "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "calls": self._extract_function_calls(node),
                    "imports": []
                }
                functions.append(func_info)
        
        return functions
    
    def extract_imports(self, tree: ast.Module) -> List[str]:
        """
        Extract import statements.
        
        Args:
            tree: AST Module
        
        Returns:
            List of imported module names
        """
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        
        return list(set(imports))
    
    def extract_api_endpoints(self, tree: ast.Module, code: str) -> List[Dict[str, Any]]:
        """
        Extract FastAPI endpoint definitions.
        
        Args:
            tree: AST Module
            code: Source code
        
        Returns:
            List of endpoint info dicts
        """
        endpoints = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check for FastAPI decorators
                for decorator in node.decorator_list:
                    decorator_name = self._get_decorator_name(decorator)
                    
                    if decorator_name in ['post', 'get', 'put', 'delete', 'patch']:
                        # Extract route path
                        path = self._extract_route_path(decorator)
                        
                        endpoints.append({
                            "method": decorator_name.upper(),
                            "path": path,
                            "function": node.name,
                            "line": node.lineno
                        })
        
        return endpoints
    
    def _get_decorator_name(self, decorator: ast.expr) -> str:
        """Extract decorator name from AST node."""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                return decorator.func.attr
            elif isinstance(decorator.func, ast.Name):
                return decorator.func.id
        elif isinstance(decorator, ast.Attribute):
            return decorator.attr
        return ""
    
    def _extract_route_path(self, decorator: ast.expr) -> str:
        """Extract route path from FastAPI decorator."""
        if isinstance(decorator, ast.Call) and len(decorator.args) > 0:
            if isinstance(decorator.args[0], ast.Constant):
                return decorator.args[0].value
        return "/"
    
    def _extract_function_calls(self, func_node: ast.FunctionDef) -> List[str]:
        """Extract function calls within a function."""
        calls = []
        
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
        
        return list(set(calls))
    
    def analyze_function_security(self, func_info: Dict[str, Any]) -> Dict[str, bool]:
        """
        Analyze function for security characteristics.
        
        Args:
            func_info: Function information dict
        
        Returns:
            Dict with security flags
        """
        calls = func_info.get("calls", [])
        params = func_info.get("parameters", [])
        
        return {
            "calls_llm": any(keyword in str(calls).lower() for keyword in ["chat", "complete", "generate", "llm"]),
            "accesses_database": any(keyword in str(calls).lower() for keyword in ["query", "execute", "session", "commit"]),
            "handles_user_input": any(keyword in params for keyword in ["request", "message", "input", "user"]),
            "has_validation": any(keyword in str(calls).lower() for keyword in ["validate", "sanitize", "clean", "escape"])
        }
