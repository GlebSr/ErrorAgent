"""LangGraph state machine for diagnostic workflow."""

from typing import Dict, Any, List
from pathlib import Path

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from ..agent.schemas import AgentState, Hypothesis, DiagnosticReport
from ..ingest.git import GitAnalyzer
from ..ingest.tests import TestArtifactParser
from ..ingest.ci import CILogParser
from ..index.code_graph import CodeGraphBuilder
from ..index.vector_store import CodeVectorStore
from .prompts import HypothesisGenerator
from .ranking import HypothesisRanker


class DiagnosticAgent:
    """Main diagnostic agent using LangGraph."""
    
    def __init__(self, llm: Any = None):
        """Initialize agent.
        
        Args:
            llm: LangChain LLM instance (optional, will use default)
        """
        self.llm = llm
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build LangGraph state machine."""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("ingest_changes", self.ingest_changes)
        workflow.add_node("ingest_failures", self.ingest_failures)
        workflow.add_node("build_index", self.build_index)
        workflow.add_node("correlate", self.correlate_data)
        workflow.add_node("generate_hypotheses", self.generate_hypotheses)
        workflow.add_node("rank_and_validate", self.rank_and_validate)
        workflow.add_node("finalize", self.finalize_report)
        
        # Add edges
        workflow.set_entry_point("ingest_changes")
        workflow.add_edge("ingest_changes", "ingest_failures")
        workflow.add_edge("ingest_failures", "build_index")
        workflow.add_edge("build_index", "correlate")
        workflow.add_edge("correlate", "generate_hypotheses")
        workflow.add_edge("generate_hypotheses", "rank_and_validate")
        workflow.add_edge("rank_and_validate", "finalize")
        workflow.add_edge("finalize", END)
        
        return workflow.compile()
    
    def ingest_changes(self, state: AgentState) -> Dict[str, Any]:
        """Ingest git changes."""
        print("📥 Ingesting git changes...")
        
        try:
            git_analyzer = GitAnalyzer(state.repo_path)
            
            # Parse changes
            code_changes = git_analyzer.parse_changes(
                base=state.base_commit,
                head=state.head_commit
            )
            
            state.code_changes = code_changes
            state.current_step = "ingest_failures"
            
            print(f"✅ Found {len(code_changes)} changed files")
            
        except Exception as e:
            state.errors.append(f"Git ingestion failed: {e}")
            print(f"❌ Error: {e}")
        
        return {"code_changes": state.code_changes, "current_step": state.current_step, "errors": state.errors}
    
    def ingest_failures(self, state: AgentState) -> Dict[str, Any]:
        """Ingest test failures and CI logs."""
        print("📥 Ingesting failure symptoms...")
        
        failure_symptoms = []
        
        # Parse test artifacts
        if state.test_artifacts_path:
            try:
                test_path = Path(state.test_artifacts_path)
                
                if test_path.suffix == '.xml':
                    symptoms = TestArtifactParser.parse_junit_xml(str(test_path))
                    failure_symptoms.extend(symptoms)
                elif test_path.suffix == '.json':
                    symptoms = TestArtifactParser.parse_pytest_json(str(test_path))
                    failure_symptoms.extend(symptoms)
                
                print(f"✅ Found {len(symptoms)} test failures")
            except Exception as e:
                state.errors.append(f"Test parsing failed: {e}")
                print(f"⚠️  Test parsing error: {e}")
        
        # Parse CI logs
        if state.ci_logs_path:
            try:
                ci_symptoms = CILogParser.parse_log_file(state.ci_logs_path)
                failure_symptoms.extend(ci_symptoms)
                print(f"✅ Found {len(ci_symptoms)} CI errors")
            except Exception as e:
                state.errors.append(f"CI log parsing failed: {e}")
                print(f"⚠️  CI log parsing error: {e}")
        
        state.failure_symptoms = failure_symptoms
        state.current_step = "build_index"
        
        return {"failure_symptoms": state.failure_symptoms, "current_step": state.current_step, "errors": state.errors}
    
    def build_index(self, state: AgentState) -> Dict[str, Any]:
        """Build code graph and vector index."""
        print("🔨 Building code index...")
        
        try:
            # Build call graph
            graph_builder = CodeGraphBuilder(state.repo_path)
            code_graph = graph_builder.build_graph(include_tests=True)
            
            # Convert to serializable format
            state.code_graph = {
                'nodes': len(code_graph.nodes()),
                'edges': len(code_graph.edges()),
                'builder': graph_builder  # Store builder for later use
            }
            
            print(f"✅ Built graph: {len(code_graph.nodes())} nodes, {len(code_graph.edges())} edges")
            
            # Build vector store (skip if no OpenAI key)
            try:
                vector_store = CodeVectorStore(state.repo_path)
                vector_store.index_repository(include_tests=True)
                
                state.embeddings_index = {
                    'doc_count': len(vector_store.documents),
                    'store': vector_store
                }
                
                print(f"✅ Indexed {len(vector_store.documents)} code chunks")
            except Exception as e:
                print(f"⚠️  Vector indexing skipped (no API key?): {e}")
                state.embeddings_index = None
            
            state.current_step = "correlate"
            
        except Exception as e:
            state.errors.append(f"Index building failed: {e}")
            print(f"❌ Error: {e}")
        
        return {"code_graph": state.code_graph, "embeddings_index": state.embeddings_index, "current_step": state.current_step, "errors": state.errors}
    
    def correlate_data(self, state: AgentState) -> Dict[str, Any]:
        """Correlate changes with failures and usages."""
        print("🔗 Correlating changes with failures...")
        
        # This step enriches the data by finding connections
        # between code changes and failure symptoms
        
        try:
            if state.code_graph and 'builder' in state.code_graph:
                graph_builder = state.code_graph['builder']
                
                # For each changed symbol, find usages
                for change in state.code_changes:
                    for symbol in change.changed_symbols:
                        usages = graph_builder.find_usages(symbol)
                        
                        # Store in metadata (would normally enrich the change object)
                        if usages:
                            print(f"  📍 Symbol '{symbol}' used in {len(usages)} places")
            
            state.current_step = "generate_hypotheses"
            
        except Exception as e:
            state.errors.append(f"Correlation failed: {e}")
            print(f"❌ Error: {e}")
        
        return {"current_step": state.current_step, "errors": state.errors}
    
    def generate_hypotheses(self, state: AgentState) -> Dict[str, Any]:
        """Generate diagnostic hypotheses using LLM."""
        print("🤔 Generating hypotheses...")
        
        try:
            generator = HypothesisGenerator(llm=self.llm)
            
            # Generate hypotheses
            hypotheses = generator.generate(
                code_changes=state.code_changes,
                failure_symptoms=state.failure_symptoms,
                code_graph=state.code_graph,
                embeddings_index=state.embeddings_index
            )
            
            state.hypotheses = hypotheses
            state.current_step = "rank_and_validate"
            
            print(f"✅ Generated {len(hypotheses)} hypotheses")
            
        except Exception as e:
            state.errors.append(f"Hypothesis generation failed: {e}")
            print(f"❌ Error: {e}")
            state.hypotheses = []
        
        return {"hypotheses": state.hypotheses, "current_step": state.current_step, "errors": state.errors}
    
    def rank_and_validate(self, state: AgentState) -> Dict[str, Any]:
        """Rank and validate hypotheses."""
        print("📊 Ranking hypotheses...")
        
        try:
            ranker = HypothesisRanker()
            
            # Rank hypotheses
            ranked_hypotheses = ranker.rank(
                hypotheses=state.hypotheses,
                code_changes=state.code_changes,
                failure_symptoms=state.failure_symptoms
            )
            
            # Keep top N
            state.hypotheses = ranked_hypotheses[:5]
            state.current_step = "finalize"
            
            print(f"✅ Ranked top {len(state.hypotheses)} hypotheses")
            
        except Exception as e:
            state.errors.append(f"Ranking failed: {e}")
            print(f"❌ Error: {e}")
        
        return {"hypotheses": state.hypotheses, "current_step": state.current_step, "errors": state.errors}
    
    def finalize_report(self, state: AgentState) -> Dict[str, Any]:
        """Create final diagnostic report."""
        print("📋 Finalizing report...")
        
        try:
            # Create summary
            summary = self._create_summary(state)
            
            # Create report
            report = DiagnosticReport(
                hypotheses=state.hypotheses,
                summary=summary,
                metadata={
                    'repo_path': state.repo_path,
                    'base_commit': state.base_commit,
                    'head_commit': state.head_commit,
                    'changes_count': len(state.code_changes),
                    'failures_count': len(state.failure_symptoms),
                    'errors': state.errors
                }
            )
            
            state.final_report = report
            state.current_step = "complete"
            
            print("✅ Report complete!")
            
        except Exception as e:
            state.errors.append(f"Report creation failed: {e}")
            print(f"❌ Error: {e}")
        
        return {"final_report": state.final_report, "current_step": state.current_step, "errors": state.errors}
    
    def _create_summary(self, state: AgentState) -> str:
        """Create executive summary."""
        lines = []
        
        lines.append(f"Analyzed {len(state.code_changes)} code changes.")
        lines.append(f"Found {len(state.failure_symptoms)} failure symptoms.")
        lines.append(f"Generated {len(state.hypotheses)} diagnostic hypotheses.")
        
        if state.hypotheses:
            top = state.hypotheses[0]
            lines.append(f"\nMost likely cause: {top.title}")
            lines.append(f"Confidence: {top.confidence:.0%}")
        
        return "\n".join(lines)
    
    def run(self, initial_state: AgentState, config: RunnableConfig = None) -> DiagnosticReport:
        """Run diagnostic analysis.
        
        Args:
            initial_state: Initial agent state
            config: LangChain runnable config
            
        Returns:
            DiagnosticReport
        """
        print("\n🚀 Starting ErrorAgent diagnostic analysis...\n")
        
        # Run graph
        final_state = self.graph.invoke(initial_state, config=config)
        
        return final_state.get('final_report') or DiagnosticReport(
            hypotheses=[],
            summary="Analysis failed",
            metadata={'errors': final_state.get('errors', [])}
        )
