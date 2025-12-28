"""Test artifact parsing (pytest XML/JSON, coverage)."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional

from ..agent.schemas import FailureSymptom


class TestArtifactParser:
    """Parses pytest outputs and coverage reports."""
    
    @staticmethod
    def parse_junit_xml(xml_path: str) -> List[FailureSymptom]:
        """Parse pytest JUnit XML output.
        
        Args:
            xml_path: Path to junit XML file
            
        Returns:
            List of FailureSymptom objects for failed tests
        """
        symptoms = []
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Find all testcase elements with failures or errors
            for testcase in root.iter('testcase'):
                classname = testcase.get('classname', '')
                name = testcase.get('name', '')
                file = testcase.get('file', '')
                
                # Check for failure
                failure = testcase.find('failure')
                error = testcase.find('error')
                
                if failure is not None:
                    message = failure.get('message', '')
                    text = failure.text or ''
                    
                    symptoms.append(FailureSymptom(
                        symptom_type="test_failure",
                        location=f"{file}::{classname}::{name}",
                        error_message=f"{message}\n{text[:500]}",
                        failing_assertion=message
                    ))
                
                if error is not None:
                    message = error.get('message', '')
                    text = error.text or ''
                    
                    symptoms.append(FailureSymptom(
                        symptom_type="test_failure",
                        location=f"{file}::{classname}::{name}",
                        error_message=f"{message}\n{text[:500]}",
                        failing_assertion=None
                    ))
        
        except Exception as e:
            raise ValueError(f"Failed to parse JUnit XML: {e}")
        
        return symptoms
    
    @staticmethod
    def parse_pytest_json(json_path: str) -> List[FailureSymptom]:
        """Parse pytest-json-report output.
        
        Args:
            json_path: Path to pytest JSON report
            
        Returns:
            List of FailureSymptom objects
        """
        symptoms = []
        
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # Parse test results
            for test_id, test_data in data.get('tests', {}).items():
                outcome = test_data.get('outcome', '')
                
                if outcome in ('failed', 'error'):
                    call_data = test_data.get('call', {})
                    
                    # Extract location
                    location = test_data.get('nodeid', test_id)
                    
                    # Extract error details
                    longrepr = call_data.get('longrepr', '')
                    crash = call_data.get('crash', {})
                    
                    error_msg = longrepr or crash.get('message', '')
                    
                    # Try to extract assertion
                    assertion = None
                    if 'AssertionError' in error_msg:
                        lines = error_msg.split('\n')
                        for line in lines:
                            if 'assert' in line.lower():
                                assertion = line.strip()
                                break
                    
                    symptoms.append(FailureSymptom(
                        symptom_type="test_failure",
                        location=location,
                        error_message=error_msg[:500],
                        failing_assertion=assertion
                    ))
        
        except Exception as e:
            raise ValueError(f"Failed to parse pytest JSON: {e}")
        
        return symptoms
    
    @staticmethod
    def parse_coverage_json(coverage_path: str) -> Dict[str, float]:
        """Parse coverage.py JSON output.
        
        Args:
            coverage_path: Path to coverage JSON file
            
        Returns:
            Dict mapping file paths to coverage percentages
        """
        coverage_map = {}
        
        try:
            with open(coverage_path, 'r') as f:
                data = json.load(f)
            
            files = data.get('files', {})
            
            for file_path, file_data in files.items():
                summary = file_data.get('summary', {})
                percent = summary.get('percent_covered', 0.0)
                coverage_map[file_path] = percent
        
        except Exception as e:
            raise ValueError(f"Failed to parse coverage JSON: {e}")
        
        return coverage_map
    
    @staticmethod
    def find_low_coverage_files(
        coverage_map: Dict[str, float],
        threshold: float = 50.0
    ) -> List[str]:
        """Find files with coverage below threshold.
        
        Args:
            coverage_map: File to coverage percentage mapping
            threshold: Coverage threshold (default 50%)
            
        Returns:
            List of file paths with low coverage
        """
        return [
            file_path
            for file_path, coverage in coverage_map.items()
            if coverage < threshold
        ]
