"""Example usage of ErrorAgent."""

from pathlib import Path
from src.agent.schemas import AgentState
from src.agent.graph import DiagnosticAgent


def main():
    """Run ErrorAgent on current repository."""
    
    # Configure analysis
    state = AgentState(
        repo_path=str(Path.cwd()),
        base_commit="HEAD~1",
        head_commit="HEAD",
        # Optional: add test artifacts and CI logs
        # test_artifacts_path="test_results.xml",
        # ci_logs_path="ci_logs.txt",
    )
    
    # Create agent
    print("🚀 Initializing ErrorAgent...")
    agent = DiagnosticAgent()
    
    # Run analysis
    print("\n📊 Running diagnostic analysis...\n")
    report = agent.run(state)
    
    # Display results
    print("\n" + "="*80)
    print("📋 DIAGNOSTIC REPORT")
    print("="*80)
    
    print(f"\n{report.summary}\n")
    
    if not report.hypotheses:
        print("❌ No hypotheses generated. Ensure there are code changes and failures to analyze.")
        return
    
    # Show each hypothesis
    for hyp in report.hypotheses:
        print(f"\n{'='*80}")
        print(f"🎯 Hypothesis #{hyp.rank}: {hyp.title}")
        print(f"Confidence: {hyp.confidence:.0%}")
        print(f"{'='*80}\n")
        
        print("🔗 Causal Chain:")
        print(f"  What Changed: {hyp.causal_chain.change}")
        print(f"  Where Used:   {hyp.causal_chain.usage}")
        print(f"  Why It Broke: {hyp.causal_chain.break_reason}")
        print(f"  First Check:  {hyp.causal_chain.first_check}")
        
        if hyp.verification_steps:
            print(f"\n✅ Verification Steps:")
            for i, step in enumerate(hyp.verification_steps, 1):
                print(f"  {i}. {step}")
        
        if hyp.related_files:
            print(f"\n📂 Files to Examine:")
            for file_path in hyp.related_files:
                print(f"  - {file_path}")
    
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()
