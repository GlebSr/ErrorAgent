"""Hypothesis ranking and validation."""

from typing import List, Dict
import re

from ..agent.schemas import Hypothesis, CodeChange, FailureSymptom


class HypothesisRanker:
    """Ranks and validates hypotheses based on evidence."""
    
    def rank(
        self,
        hypotheses: List[Hypothesis],
        code_changes: List[CodeChange],
        failure_symptoms: List[FailureSymptom]
    ) -> List[Hypothesis]:
        """Rank hypotheses by likelihood.
        
        Args:
            hypotheses: List of hypotheses to rank
            code_changes: Code changes
            failure_symptoms: Failure symptoms
            
        Returns:
            Sorted list of hypotheses (best first)
        """
        if not hypotheses:
            return []
        
        # Calculate ranking score for each hypothesis
        scored_hypotheses = []
        
        for hyp in hypotheses:
            score = self._calculate_score(hyp, code_changes, failure_symptoms)
            scored_hypotheses.append((score, hyp))
        
        # Sort by score (descending)
        scored_hypotheses.sort(key=lambda x: x[0], reverse=True)
        
        # Update ranks and return
        ranked = []
        for rank, (score, hyp) in enumerate(scored_hypotheses, 1):
            hyp.rank = rank
            # Update confidence based on score
            hyp.confidence = min(1.0, score / 10.0)  # Normalize to 0-1
            ranked.append(hyp)
        
        return ranked
    
    def _calculate_score(
        self,
        hypothesis: Hypothesis,
        code_changes: List[CodeChange],
        failure_symptoms: List[FailureSymptom]
    ) -> float:
        """Calculate ranking score for a hypothesis.
        
        Higher score = more likely cause.
        """
        score = 0.0
        
        # Base score from LLM confidence
        score += hypothesis.confidence * 3.0
        
        # Bonus for specific file matches
        hyp_files = set(hypothesis.related_files)
        changed_files = {c.file_path for c in code_changes}
        failure_files = {self._extract_file(s.location) for s in failure_symptoms}
        
        # Direct overlap between changed files and failure locations
        direct_overlap = hyp_files & changed_files & failure_files
        score += len(direct_overlap) * 2.0
        
        # Partial overlap
        changed_overlap = hyp_files & changed_files
        score += len(changed_overlap) * 1.0
        
        failure_overlap = hyp_files & failure_files
        score += len(failure_overlap) * 1.5
        
        # Bonus for symbol matches
        symbol_score = self._score_symbol_matches(hypothesis, code_changes, failure_symptoms)
        score += symbol_score
        
        # Bonus for detailed causal chain
        if hypothesis.causal_chain:
            chain = hypothesis.causal_chain
            if len(chain.change) > 20 and len(chain.usage) > 20:
                score += 1.0
            if len(chain.break_reason) > 30:
                score += 0.5
        
        # Bonus for specific verification steps
        if hypothesis.verification_steps:
            if len(hypothesis.verification_steps) >= 3:
                score += 0.5
        
        # Penalty for vague language
        if self._is_vague(hypothesis):
            score -= 1.0
        
        return max(0.0, score)
    
    def _extract_file(self, location: str) -> str:
        """Extract file path from location string."""
        # Handle formats like "file.py::TestClass::test_method" or "file.py:123"
        if '::' in location:
            return location.split('::')[0]
        elif ':' in location:
            return location.split(':')[0]
        return location
    
    def _score_symbol_matches(
        self,
        hypothesis: Hypothesis,
        code_changes: List[CodeChange],
        failure_symptoms: List[FailureSymptom]
    ) -> float:
        """Score based on symbol name matches."""
        score = 0.0
        
        # Extract all symbols mentioned in hypothesis
        hyp_text = (
            hypothesis.title + " " +
            hypothesis.causal_chain.change + " " +
            hypothesis.causal_chain.usage
        )
        
        # Get changed symbols
        changed_symbols = set()
        for change in code_changes:
            changed_symbols.update(change.changed_symbols)
        
        # Check for symbol mentions
        for symbol in changed_symbols:
            if symbol in hyp_text:
                score += 1.0
        
        # Check for symbol mentions in error messages
        for symptom in failure_symptoms:
            for symbol in changed_symbols:
                if symbol in symptom.error_message:
                    score += 0.5
        
        return score
    
    def _is_vague(self, hypothesis: Hypothesis) -> bool:
        """Check if hypothesis is too vague."""
        vague_phrases = [
            'may have',
            'might be',
            'could be',
            'possibly',
            'perhaps',
            'unknown',
            'unclear',
            'not sure'
        ]
        
        text = (
            hypothesis.title.lower() + " " +
            hypothesis.causal_chain.change.lower() + " " +
            hypothesis.causal_chain.break_reason.lower()
        )
        
        vague_count = sum(1 for phrase in vague_phrases if phrase in text)
        
        return vague_count >= 3
    
    def validate_hypothesis(
        self,
        hypothesis: Hypothesis,
        code_changes: List[CodeChange],
        failure_symptoms: List[FailureSymptom]
    ) -> Dict[str, any]:
        """Validate hypothesis against evidence.
        
        Args:
            hypothesis: Hypothesis to validate
            code_changes: Code changes
            failure_symptoms: Failure symptoms
            
        Returns:
            Dict with validation results
        """
        validation = {
            'valid': True,
            'issues': [],
            'strengths': []
        }
        
        # Check if related files actually changed
        changed_files = {c.file_path for c in code_changes}
        unmatched_files = set(hypothesis.related_files) - changed_files
        
        if len(unmatched_files) == len(hypothesis.related_files):
            validation['issues'].append("None of the related files were actually changed")
            validation['valid'] = False
        elif unmatched_files:
            validation['issues'].append(f"Some files not changed: {unmatched_files}")
        else:
            validation['strengths'].append("All related files were changed")
        
        # Check if hypothesis mentions specific errors
        error_messages = [s.error_message for s in failure_symptoms]
        mentions_error = any(
            err[:50] in hypothesis.causal_chain.break_reason
            for err in error_messages
        )
        
        if mentions_error:
            validation['strengths'].append("References actual error messages")
        
        # Check verification steps
        if not hypothesis.verification_steps:
            validation['issues'].append("No verification steps provided")
        elif len(hypothesis.verification_steps) < 2:
            validation['issues'].append("Too few verification steps")
        else:
            validation['strengths'].append(f"{len(hypothesis.verification_steps)} verification steps")
        
        return validation
