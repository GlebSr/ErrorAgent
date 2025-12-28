"""CI log parsing and error extraction."""

import re
from pathlib import Path
from typing import List, Dict, Optional

from ..agent.schemas import FailureSymptom


class CILogParser:
    """Parses CI/CD logs for errors and failures."""
    
    # Common error patterns
    ERROR_PATTERNS = [
        r'ERROR:?\s+(.+)',
        r'FAILED:?\s+(.+)',
        r'Error:\s+(.+)',
        r'Exception:\s+(.+)',
        r'Traceback \(most recent call last\):',
        r'\[ERROR\]\s+(.+)',
        r'Build FAILED',
        r'npm ERR!\s+(.+)',
        r'fatal:\s+(.+)',
    ]
    
    # Compilation/build errors
    BUILD_ERROR_PATTERNS = [
        r'error:\s+(.+)',  # Compiler errors
        r'SyntaxError:\s+(.+)',
        r'ImportError:\s+(.+)',
        r'ModuleNotFoundError:\s+(.+)',
        r'TypeError:\s+(.+)',
        r'AttributeError:\s+(.+)',
    ]
    
    @staticmethod
    def parse_log_file(log_path: str) -> List[FailureSymptom]:
        """Parse CI log file for errors.
        
        Args:
            log_path: Path to log file
            
        Returns:
            List of FailureSymptom objects
        """
        symptoms = []
        
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            raise ValueError(f"Failed to read log file: {e}")
        
        # Scan for error patterns
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Check all error patterns
            for pattern in CILogParser.ERROR_PATTERNS + CILogParser.BUILD_ERROR_PATTERNS:
                match = re.search(pattern, line, re.IGNORECASE)
                
                if match:
                    # Extract context (5 lines around error)
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    context = ''.join(lines[start:end])
                    
                    # Determine symptom type
                    symptom_type = "ci_error"
                    if any(p in line.lower() for p in ['test', 'assertion', 'failed']):
                        symptom_type = "test_failure"
                    elif any(p in line.lower() for p in ['error:', 'exception', 'traceback']):
                        symptom_type = "runtime_error"
                    
                    # Extract location if present (file:line format)
                    location = "CI log"
                    file_match = re.search(r'([a-zA-Z0-9_/.-]+\.py):(\d+)', context)
                    if file_match:
                        location = f"{file_match.group(1)}:{file_match.group(2)}"
                    
                    symptoms.append(FailureSymptom(
                        symptom_type=symptom_type,
                        location=location,
                        error_message=context[:500],
                        failing_assertion=match.group(1) if match.lastindex else None
                    ))
                    
                    break  # Only match first pattern per line
        
        return symptoms
    
    @staticmethod
    def extract_stack_traces(log_path: str) -> List[Dict[str, str]]:
        """Extract Python stack traces from logs.
        
        Args:
            log_path: Path to log file
            
        Returns:
            List of dicts with 'trace' and 'error' keys
        """
        traces = []
        
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            raise ValueError(f"Failed to read log file: {e}")
        
        # Find all stack traces
        trace_pattern = r'Traceback \(most recent call last\):(.*?)(?:\n[A-Z][a-zA-Z]*Error: .+)'
        matches = re.finditer(trace_pattern, content, re.DOTALL)
        
        for match in matches:
            trace_text = match.group(0)
            
            # Extract final error line
            error_match = re.search(r'\n([A-Z][a-zA-Z]*Error: .+)$', trace_text)
            error = error_match.group(1) if error_match else "Unknown error"
            
            traces.append({
                'trace': trace_text[:1000],
                'error': error
            })
        
        return traces
    
    @staticmethod
    def parse_github_actions_log(log_path: str) -> List[FailureSymptom]:
        """Parse GitHub Actions log format.
        
        Args:
            log_path: Path to GitHub Actions log
            
        Returns:
            List of FailureSymptom objects
        """
        # GitHub Actions logs have special markers
        # ::error file={name},line={line},col={col}::{message}
        
        symptoms = []
        
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            raise ValueError(f"Failed to read log file: {e}")
        
        # Parse GitHub Actions error format
        error_pattern = r'::error file=([^,]+)(?:,line=(\d+))?(?:,col=(\d+))?::(.+)'
        matches = re.finditer(error_pattern, content)
        
        for match in matches:
            file_path = match.group(1)
            line = match.group(2) or '?'
            message = match.group(4)
            
            location = f"{file_path}:{line}"
            
            symptoms.append(FailureSymptom(
                symptom_type="ci_error",
                location=location,
                error_message=message[:500],
                failing_assertion=None
            ))
        
        # Also parse regular errors
        symptoms.extend(CILogParser.parse_log_file(log_path))
        
        return symptoms
