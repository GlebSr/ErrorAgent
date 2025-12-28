"""Pydantic schemas for structured agent outputs."""

from typing import List, Optional
from pydantic import BaseModel, Field


class CodeChange(BaseModel):
    """Represents a code change from git diff."""
    
    file_path: str = Field(description="Path to the changed file")
    change_type: str = Field(description="Type: added, modified, deleted")
    lines_added: int = Field(default=0, description="Number of lines added")
    lines_removed: int = Field(default=0, description="Number of lines removed")
    changed_symbols: List[str] = Field(
        default_factory=list,
        description="Functions/classes/variables modified"
    )
    diff_snippet: str = Field(description="Relevant diff snippet")


class UsageLocation(BaseModel):
    """Where a symbol is used in the codebase."""
    
    file_path: str = Field(description="File containing usage")
    line_number: int = Field(description="Line number of usage")
    context: str = Field(description="Code context around usage")
    is_test: bool = Field(default=False, description="Whether this is in test code")


class FailureSymptom(BaseModel):
    """Test failure or CI error symptom."""
    
    symptom_type: str = Field(description="Type: test_failure, ci_error, runtime_error")
    location: str = Field(description="File/test where failure occurred")
    error_message: str = Field(description="Error message or stack trace snippet")
    failing_assertion: Optional[str] = Field(
        default=None,
        description="The specific assertion that failed"
    )


class CausalChain(BaseModel):
    """Cause-effect chain explaining the failure."""
    
    change: str = Field(description="What was changed")
    usage: str = Field(description="Where/how it's used")
    break_reason: str = Field(description="Why this causes the failure")
    first_check: str = Field(description="First thing to verify/check")


class Hypothesis(BaseModel):
    """A single diagnostic hypothesis with causal chain."""
    
    rank: int = Field(description="Ranking (1 = most likely)")
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score 0-1"
    )
    title: str = Field(description="Short hypothesis title")
    
    # Causal chain
    code_changes: List[CodeChange] = Field(
        description="Related code changes"
    )
    affected_usages: List[UsageLocation] = Field(
        description="Usages affected by changes"
    )
    failure_symptoms: List[FailureSymptom] = Field(
        description="Related failure symptoms"
    )
    causal_chain: CausalChain = Field(
        description="Step-by-step causal explanation"
    )
    
    # Actionable checks
    verification_steps: List[str] = Field(
        description="Ordered steps to verify this hypothesis"
    )
    related_files: List[str] = Field(
        description="Files to examine"
    )


class DiagnosticReport(BaseModel):
    """Complete diagnostic analysis output."""
    
    hypotheses: List[Hypothesis] = Field(
        description="Top N hypotheses, ordered by rank"
    )
    summary: str = Field(
        description="Executive summary of analysis"
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Analysis metadata (timestamp, repo, commit)"
    )


class AgentState(BaseModel):
    """State for LangGraph agent workflow."""
    
    # Inputs
    repo_path: str
    base_commit: Optional[str] = None
    head_commit: Optional[str] = None
    test_artifacts_path: Optional[str] = None
    ci_logs_path: Optional[str] = None
    
    # Intermediate data
    raw_diffs: List[dict] = Field(default_factory=list)
    code_changes: List[CodeChange] = Field(default_factory=list)
    failure_symptoms: List[FailureSymptom] = Field(default_factory=list)
    code_graph: Optional[dict] = None
    embeddings_index: Optional[dict] = None
    
    # Outputs
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    final_report: Optional[DiagnosticReport] = None
    
    # Control
    current_step: str = "init"
    errors: List[str] = Field(default_factory=list)
