"""Prompt templates for hypothesis generation."""

from typing import List, Any, Optional
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from ..agent.schemas import (
    Hypothesis, CausalChain, CodeChange,
    FailureSymptom, UsageLocation
)


class HypothesisGenerator:
    """Generates diagnostic hypotheses using LLM."""
    
    SYSTEM_PROMPT = """You are an expert software debugging assistant specializing in root cause analysis.

Your task is to analyze code changes, test failures, and CI errors to generate plausible hypotheses 
explaining why the failures occurred. For each hypothesis, provide:

1. **What changed**: Specific code modifications
2. **Where it's used**: How and where the changed code is utilized
3. **Why it broke**: Causal chain linking change to failure
4. **What to check first**: Specific, actionable verification steps

Focus on:
- Direct dependencies and call chains
- Type mismatches and interface changes
- Missing error handling
- State/timing issues
- Configuration changes
- Test-specific issues (fixtures, mocks, data)

Be specific and technical. Prioritize hypotheses based on:
- Proximity of changes to failures
- Common failure patterns
- Complexity of changes
"""
    
    HYPOTHESIS_PROMPT = """Based on the following information, generate 3-5 diagnostic hypotheses.

## Code Changes
{code_changes}

## Failure Symptoms
{failure_symptoms}

## Code Usage Context
{usage_context}

For each hypothesis, provide:
- Title (short, specific)
- Confidence score (0.0-1.0)
- Detailed causal chain (change → usage → break reason → first check)
- Verification steps (ordered list)
- Related files to examine

Output a JSON array of hypotheses following this schema:
{format_instructions}

Focus on the most likely causes based on the evidence provided.
"""
    
    def __init__(self, llm: Optional[Any] = None):
        """Initialize hypothesis generator.
        
        Args:
            llm: LangChain LLM instance
        """
        if llm is None:
            # Default to OpenAI
            try:
                from langchain_openai import ChatOpenAI
                self.llm = ChatOpenAI(model="gpt-4o", temperature=0.2)
            except ImportError:
                raise ImportError("Install langchain-openai: pip install langchain-openai")
        else:
            self.llm = llm
        
        # Output parser
        self.parser = PydanticOutputParser(pydantic_object=List[Hypothesis])
        
        # Create prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("user", self.HYPOTHESIS_PROMPT)
        ])
    
    def format_code_changes(self, changes: List[CodeChange]) -> str:
        """Format code changes for prompt."""
        if not changes:
            return "No code changes detected."
        
        lines = []
        for i, change in enumerate(changes[:10], 1):  # Limit to 10
            lines.append(f"\n### Change {i}: {change.file_path}")
            lines.append(f"Type: {change.change_type}")
            lines.append(f"Lines: +{change.lines_added}, -{change.lines_removed}")
            
            if change.changed_symbols:
                lines.append(f"Symbols: {', '.join(change.changed_symbols)}")
            
            lines.append(f"\n```diff\n{change.diff_snippet}\n```")
        
        return "\n".join(lines)
    
    def format_failure_symptoms(self, symptoms: List[FailureSymptom]) -> str:
        """Format failure symptoms for prompt."""
        if not symptoms:
            return "No failure symptoms provided."
        
        lines = []
        for i, symptom in enumerate(symptoms[:10], 1):  # Limit to 10
            lines.append(f"\n### Failure {i}: {symptom.symptom_type}")
            lines.append(f"Location: {symptom.location}")
            
            if symptom.failing_assertion:
                lines.append(f"Assertion: {symptom.failing_assertion}")
            
            lines.append(f"\n```\n{symptom.error_message}\n```")
        
        return "\n".join(lines)
    
    def format_usage_context(self, code_graph: Optional[dict], changes: List[CodeChange]) -> str:
        """Format usage context from code graph."""
        if not code_graph or 'builder' not in code_graph:
            return "Usage context not available."
        
        graph_builder = code_graph['builder']
        lines = []
        
        # Get usages for changed symbols
        for change in changes[:5]:  # Limit
            for symbol in change.changed_symbols[:3]:  # Limit per file
                usages = graph_builder.find_usages(symbol)
                
                if usages:
                    lines.append(f"\n### Symbol: {symbol}")
                    lines.append(f"Used in {len(usages)} locations:")
                    
                    for usage in usages[:5]:  # Top 5 usages
                        test_marker = " [TEST]" if usage.is_test else ""
                        lines.append(f"\n- {usage.file_path}:{usage.line_number}{test_marker}")
                        lines.append(f"  ```python\n  {usage.context}\n  ```")
        
        return "\n".join(lines) if lines else "No usage information found."
    
    def generate(
        self,
        code_changes: List[CodeChange],
        failure_symptoms: List[FailureSymptom],
        code_graph: Optional[dict] = None,
        embeddings_index: Optional[dict] = None
    ) -> List[Hypothesis]:
        """Generate hypotheses.
        
        Args:
            code_changes: List of code changes
            failure_symptoms: List of failure symptoms
            code_graph: Code graph dict (optional)
            embeddings_index: Vector store dict (optional)
            
        Returns:
            List of Hypothesis objects
        """
        # Format inputs
        changes_text = self.format_code_changes(code_changes)
        symptoms_text = self.format_failure_symptoms(failure_symptoms)
        usage_text = self.format_usage_context(code_graph, code_changes)
        
        # Create prompt
        messages = self.prompt.format_messages(
            code_changes=changes_text,
            failure_symptoms=symptoms_text,
            usage_context=usage_text,
            format_instructions=self.parser.get_format_instructions()
        )
        
        # Generate
        try:
            response = self.llm.invoke(messages)
            
            # Parse output
            hypotheses = self.parser.parse(response.content)
            
            # Ensure ranking
            for i, hyp in enumerate(hypotheses, 1):
                if hyp.rank == 0:
                    hyp.rank = i
            
            return hypotheses
            
        except Exception as e:
            print(f"⚠️  LLM generation failed: {e}")
            
            # Return fallback hypothesis
            return [self._create_fallback_hypothesis(code_changes, failure_symptoms)]
    
    def _create_fallback_hypothesis(
        self,
        code_changes: List[CodeChange],
        failure_symptoms: List[FailureSymptom]
    ) -> Hypothesis:
        """Create a simple rule-based hypothesis as fallback."""
        
        # Find most changed file
        if code_changes:
            main_change = max(code_changes, key=lambda c: c.lines_added + c.lines_removed)
            changed_file = main_change.file_path
            symbols = main_change.changed_symbols
        else:
            changed_file = "unknown"
            symbols = []
        
        # Find most common failure
        if failure_symptoms:
            main_symptom = failure_symptoms[0]
            failure_loc = main_symptom.location
            error_msg = main_symptom.error_message[:200]
        else:
            failure_loc = "unknown"
            error_msg = "No error details"
        
        return Hypothesis(
            rank=1,
            confidence=0.5,
            title=f"Changes in {changed_file} may have caused failures",
            code_changes=code_changes[:3],
            affected_usages=[],
            failure_symptoms=failure_symptoms[:3],
            causal_chain=CausalChain(
                change=f"Modified {changed_file}" + (f" ({', '.join(symbols[:3])})" if symbols else ""),
                usage=f"Used by tests/code at {failure_loc}",
                break_reason="Code changes may have introduced incompatibility or regression",
                first_check=f"Review changes in {changed_file} and verify test expectations"
            ),
            verification_steps=[
                f"Examine changes in {changed_file}",
                "Run affected tests in isolation",
                "Check for type/interface changes",
                "Review test fixtures and mocks"
            ],
            related_files=[changed_file, failure_loc.split('::')[0] if '::' in failure_loc else failure_loc]
        )
