"""Streamlit UI for ErrorAgent."""

import streamlit as st
from pathlib import Path
import sys
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.agent.schemas import AgentState, DiagnosticReport
from src.agent.graph import DiagnosticAgent


def main():
    """Main Streamlit app."""
    st.set_page_config(
        page_title="ErrorAgent - Code Failure Diagnostics",
        page_icon="🔍",
        layout="wide"
    )
    
    st.title("🔍 ErrorAgent")
    st.markdown("*AI-powered diagnostic tool for code failures*")
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Repository selection
        repo_path = st.text_input(
            "Repository Path",
            value=str(Path.cwd()),
            help="Path to git repository to analyze"
        )
        
        # Commit selection
        st.subheader("Git Commits")
        base_commit = st.text_input(
            "Base Commit",
            value="HEAD~1",
            help="Base commit for comparison (e.g., HEAD~1, main, commit hash)"
        )
        
        head_commit = st.text_input(
            "Head Commit",
            value="HEAD",
            help="Head commit to analyze"
        )
        
        # Test artifacts
        st.subheader("Test Artifacts")
        test_artifacts = st.file_uploader(
            "Upload Test Results",
            type=['xml', 'json'],
            help="pytest JUnit XML or JSON report"
        )
        
        # CI logs
        ci_logs = st.file_uploader(
            "Upload CI Logs",
            type=['log', 'txt'],
            help="CI/CD log file"
        )
        
        # Analysis button
        st.markdown("---")
        analyze_button = st.button("🚀 Run Analysis", type="primary", use_container_width=True)
    
    # Main content area
    if 'report' not in st.session_state:
        st.session_state.report = None
    
    if analyze_button:
        run_analysis(
            repo_path=repo_path,
            base_commit=base_commit,
            head_commit=head_commit,
            test_artifacts=test_artifacts,
            ci_logs=ci_logs
        )
    
    # Display results
    if st.session_state.report:
        display_report(st.session_state.report)
    else:
        show_welcome()


def run_analysis(
    repo_path: str,
    base_commit: str,
    head_commit: str,
    test_artifacts: Optional[any],
    ci_logs: Optional[any]
):
    """Run diagnostic analysis."""
    
    # Validate repository
    if not Path(repo_path).exists():
        st.error(f"❌ Repository path does not exist: {repo_path}")
        return
    
    # Save uploaded files temporarily
    test_path = None
    ci_path = None
    
    if test_artifacts:
        test_path = f"/tmp/test_artifacts.{test_artifacts.name.split('.')[-1]}"
        with open(test_path, 'wb') as f:
            f.write(test_artifacts.getbuffer())
    
    if ci_logs:
        ci_path = "/tmp/ci_logs.log"
        with open(ci_path, 'wb') as f:
            f.write(ci_logs.getbuffer())
    
    # Create initial state
    initial_state = AgentState(
        repo_path=repo_path,
        base_commit=base_commit if base_commit else None,
        head_commit=head_commit,
        test_artifacts_path=test_path,
        ci_logs_path=ci_path
    )
    
    # Run analysis
    with st.spinner("🔍 Analyzing code changes and failures..."):
        try:
            agent = DiagnosticAgent()
            report = agent.run(initial_state)
            st.session_state.report = report
            st.success("✅ Analysis complete!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Analysis failed: {e}")
            st.exception(e)


def display_report(report: DiagnosticReport):
    """Display diagnostic report."""
    
    # Summary
    st.header("📋 Analysis Summary")
    st.info(report.summary)
    
    # Metadata
    with st.expander("📊 Analysis Metadata"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Code Changes", report.metadata.get('changes_count', 0))
        with col2:
            st.metric("Failures Found", report.metadata.get('failures_count', 0))
        with col3:
            st.metric("Hypotheses", len(report.hypotheses))
    
    # Hypotheses
    st.header("🎯 Diagnostic Hypotheses")
    
    if not report.hypotheses:
        st.warning("No hypotheses generated. Check if there are code changes and failures to analyze.")
        return
    
    for i, hyp in enumerate(report.hypotheses):
        with st.expander(
            f"#{hyp.rank} - {hyp.title} (Confidence: {hyp.confidence:.0%})",
            expanded=(i == 0)  # Expand first hypothesis
        ):
            display_hypothesis(hyp)
    
    # Errors
    if report.metadata.get('errors'):
        with st.expander("⚠️ Errors During Analysis"):
            for error in report.metadata['errors']:
                st.warning(error)


def display_hypothesis(hyp):
    """Display a single hypothesis."""
    
    # Confidence meter
    st.progress(hyp.confidence, text=f"Confidence: {hyp.confidence:.0%}")
    
    # Causal chain
    st.subheader("🔗 Causal Chain")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**What Changed**")
        st.code(hyp.causal_chain.change, language=None)
        
        st.markdown("**Where Used**")
        st.code(hyp.causal_chain.usage, language=None)
    
    with col2:
        st.markdown("**Why It Broke**")
        st.code(hyp.causal_chain.break_reason, language=None)
        
        st.markdown("**First Check** 🎯")
        st.code(hyp.causal_chain.first_check, language=None)
    
    # Code changes
    if hyp.code_changes:
        st.subheader("📝 Related Code Changes")
        for change in hyp.code_changes[:3]:  # Show top 3
            with st.container():
                st.markdown(f"**{change.file_path}** ({change.change_type})")
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Lines Added", f"+{change.lines_added}", delta_color="off")
                col2.metric("Lines Removed", f"-{change.lines_removed}", delta_color="off")
                
                if change.changed_symbols:
                    col3.write("**Symbols:**")
                    col3.write(", ".join(change.changed_symbols[:5]))
                
                with st.expander("View Diff"):
                    st.code(change.diff_snippet, language="diff")
    
    # Failure symptoms
    if hyp.failure_symptoms:
        st.subheader("❌ Related Failures")
        for symptom in hyp.failure_symptoms[:3]:  # Show top 3
            with st.container():
                st.markdown(f"**{symptom.location}** ({symptom.symptom_type})")
                
                if symptom.failing_assertion:
                    st.code(symptom.failing_assertion, language="python")
                
                with st.expander("Error Details"):
                    st.code(symptom.error_message, language=None)
    
    # Affected usages
    if hyp.affected_usages:
        st.subheader("📍 Affected Code Locations")
        for usage in hyp.affected_usages[:5]:  # Show top 5
            test_badge = "🧪 TEST" if usage.is_test else ""
            st.markdown(f"- **{usage.file_path}:{usage.line_number}** {test_badge}")
            with st.expander("Context"):
                st.code(usage.context, language="python")
    
    # Verification steps
    st.subheader("✅ Verification Steps")
    for i, step in enumerate(hyp.verification_steps, 1):
        st.markdown(f"{i}. {step}")
    
    # Related files
    if hyp.related_files:
        st.subheader("📂 Files to Examine")
        for file_path in hyp.related_files:
            st.code(file_path, language=None)
    
    # Copy-paste command
    st.markdown("---")
    st.markdown("**Quick Check Command:**")
    if hyp.related_files:
        cmd = f"git diff HEAD~1 {' '.join(hyp.related_files[:3])}"
        st.code(cmd, language="bash")


def show_welcome():
    """Show welcome screen."""
    st.markdown("""
    ## Welcome to ErrorAgent! 👋
    
    ErrorAgent analyzes code changes and test failures to generate diagnostic hypotheses
    explaining what broke and why.
    
    ### How to use:
    
    1. **Select Repository**: Point to your git repository
    2. **Choose Commits**: Select base and head commits to compare
    3. **Upload Artifacts** (optional):
       - Test results (pytest XML/JSON)
       - CI/CD logs
    4. **Run Analysis**: Click "Run Analysis" to generate hypotheses
    
    ### What you'll get:
    
    - 🎯 **Ranked Hypotheses**: Top 3-5 most likely causes
    - 🔗 **Causal Chains**: What changed → Where used → Why broke → What to check
    - 📝 **Code Changes**: Detailed diffs and affected symbols
    - ❌ **Failure Mapping**: Links between changes and test failures
    - ✅ **Action Items**: Specific verification steps
    
    ### Features:
    
    - **Code Graph Analysis**: Understands call relationships and dependencies
    - **Semantic Search**: Finds relevant code using embeddings (requires OpenAI API key)
    - **Multi-Source**: Combines git diffs, test reports, CI logs, and coverage
    - **LLM-Powered**: Uses GPT-4 for intelligent hypothesis generation
    
    ---
    
    **Configuration Required:**
    
    For full functionality, set your OpenAI API key:
    ```bash
    export OPENAI_API_KEY=your-key-here
    ```
    
    ErrorAgent will work without an API key but with reduced semantic search capabilities.
    """)
    
    # Sample output
    with st.expander("📸 See Example Output"):
        st.image("https://via.placeholder.com/800x400.png?text=Example+Hypothesis+Output", 
                 caption="Example diagnostic hypothesis")


if __name__ == "__main__":
    main()
