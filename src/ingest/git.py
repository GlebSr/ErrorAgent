"""Git diff parsing and change extraction."""

import re
from pathlib import Path
from typing import List, Optional, Tuple
import git
from git.diff import Diff

from ..agent.schemas import CodeChange


class GitAnalyzer:
    """Analyzes git repository changes."""
    
    def __init__(self, repo_path: str):
        """Initialize with repository path."""
        self.repo_path = Path(repo_path)
        try:
            self.repo = git.Repo(repo_path)
        except git.InvalidGitRepositoryError:
            raise ValueError(f"Not a valid git repository: {repo_path}")
    
    def get_diff(
        self,
        base: Optional[str] = None,
        head: Optional[str] = "HEAD"
    ) -> List[Diff]:
        """Get diff between commits.
        
        Args:
            base: Base commit (default: HEAD~1)
            head: Head commit (default: HEAD)
            
        Returns:
            List of git.Diff objects
        """
        if base is None:
            # Default to comparing with previous commit
            base = f"{head}~1"
        
        try:
            return self.repo.commit(head).diff(base)
        except git.GitCommandError as e:
            raise ValueError(f"Failed to get diff: {e}")
    
    def extract_changed_symbols(self, diff_text: str, file_path: str) -> List[str]:
        """Extract function/class names from diff.
        
        Args:
            diff_text: The unified diff text
            file_path: Path to the file (to determine language)
            
        Returns:
            List of symbol names (functions, classes, methods)
        """
        symbols = []
        
        # Python pattern: def function_name / class ClassName
        if file_path.endswith('.py'):
            # Look for changed lines starting with def/class
            for line in diff_text.split('\n'):
                if line.startswith('+') or line.startswith('-'):
                    # Function definition
                    func_match = re.search(r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)', line)
                    if func_match:
                        symbols.append(func_match.group(1))
                    
                    # Class definition
                    class_match = re.search(r'class\s+([a-zA-Z_][a-zA-Z0-9_]*)', line)
                    if class_match:
                        symbols.append(class_match.group(1))
        
        # JavaScript/TypeScript: function/const/class
        elif file_path.endswith(('.js', '.ts', '.jsx', '.tsx')):
            for line in diff_text.split('\n'):
                if line.startswith('+') or line.startswith('-'):
                    # Function/const
                    js_match = re.search(
                        r'(?:function|const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)',
                        line
                    )
                    if js_match:
                        symbols.append(js_match.group(1))
                    
                    # Class
                    class_match = re.search(r'class\s+([a-zA-Z_$][a-zA-Z0-9_$]*)', line)
                    if class_match:
                        symbols.append(class_match.group(1))
        
        return list(set(symbols))  # Remove duplicates
    
    def parse_changes(
        self,
        base: Optional[str] = None,
        head: Optional[str] = "HEAD"
    ) -> List[CodeChange]:
        """Parse git changes into structured CodeChange objects.
        
        Args:
            base: Base commit (default: HEAD~1)
            head: Head commit (default: HEAD)
            
        Returns:
            List of CodeChange objects
        """
        diffs = self.get_diff(base, head)
        changes = []
        
        for diff_item in diffs:
            # Determine change type
            if diff_item.new_file:
                change_type = "added"
                file_path = diff_item.b_path
            elif diff_item.deleted_file:
                change_type = "deleted"
                file_path = diff_item.a_path
            elif diff_item.renamed_file:
                change_type = "renamed"
                file_path = f"{diff_item.a_path} → {diff_item.b_path}"
            else:
                change_type = "modified"
                file_path = diff_item.a_path or diff_item.b_path
            
            # Get diff text
            try:
                diff_text = diff_item.diff.decode('utf-8', errors='ignore')
            except AttributeError:
                diff_text = str(diff_item)
            
            # Count lines
            lines_added = diff_text.count('\n+')
            lines_removed = diff_text.count('\n-')
            
            # Extract changed symbols
            changed_symbols = self.extract_changed_symbols(diff_text, file_path)
            
            # Create snippet (first 500 chars)
            diff_snippet = diff_text[:500]
            if len(diff_text) > 500:
                diff_snippet += "\n... (truncated)"
            
            changes.append(CodeChange(
                file_path=file_path,
                change_type=change_type,
                lines_added=lines_added,
                lines_removed=lines_removed,
                changed_symbols=changed_symbols,
                diff_snippet=diff_snippet
            ))
        
        return changes
    
    def get_file_content(self, file_path: str, commit: str = "HEAD") -> Optional[str]:
        """Get file content at specific commit.
        
        Args:
            file_path: Path to file relative to repo root
            commit: Commit reference
            
        Returns:
            File content as string, or None if not found
        """
        try:
            return self.repo.commit(commit).tree[file_path].data_stream.read().decode('utf-8')
        except (KeyError, AttributeError):
            return None
