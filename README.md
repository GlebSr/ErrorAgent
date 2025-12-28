# ErrorAgent 🔍

AI-powered diagnostic tool that analyzes code changes and failure symptoms to generate plausible hypotheses with causal chains.

## Overview

ErrorAgent helps developers quickly diagnose code failures by:
1. Analyzing git diffs to understand what changed
2. Parsing test failures, CI logs, and coverage reports
3. Building a code usage graph and semantic index
4. Generating ranked hypotheses with causal explanations
5. Providing actionable verification steps

## Architecture

```
ErrorAgent/
├── src/
│   ├── agent/           # LangGraph orchestration & schemas
│   │   ├── schemas.py   # Pydantic models (Hypothesis, AgentState)
│   │   ├── graph.py     # LangGraph state machine
│   │   ├── prompts.py   # LLM prompt templates
│   │   └── ranking.py   # Hypothesis scoring & validation
│   ├── ingest/          # Data connectors
│   │   ├── git.py       # Git diff parsing
│   │   ├── tests.py     # pytest XML/JSON parsing
│   │   └── ci.py        # CI log parsing
│   ├── index/           # Code analysis
│   │   ├── code_graph.py    # AST & call graph builder
│   │   └── vector_store.py  # Embeddings & semantic search
│   └── ui/
│       └── app_streamlit.py # Streamlit interface
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Features

### 🎯 Hypothesis Generation
- **Causal Chains**: What changed → Where used → Why broke → What to check
- **Evidence-Based**: Links code changes to specific failures
- **Ranked by Likelihood**: Top 3-5 hypotheses with confidence scores

### 🔍 Multi-Source Analysis
- **Git Diffs**: Parses changes and extracts modified symbols
- **Test Reports**: Supports pytest JUnit XML and JSON formats
- **CI Logs**: Extracts errors from GitHub Actions, GitLab, and generic logs
- **Coverage**: Identifies low-coverage areas

### 🧠 Intelligent Indexing
- **Call Graph**: Tracks function dependencies using AST analysis
- **Usage Graph**: Finds where symbols are referenced
- **Semantic Search**: Vector embeddings for code similarity (requires OpenAI API)
- **Hybrid Search**: Combines BM25 keyword search with embeddings

### 🎨 Interactive UI
- **Streamlit Interface**: Clean, intuitive web UI
- **Drill-Down**: Expand hypotheses to see diffs, usages, and errors
- **Copy-Paste Commands**: Quick verification commands
- **Real-Time Progress**: Visual feedback during analysis

## Installation

### Prerequisites
- Python 3.9+
- Git repository to analyze
- OpenAI API key (optional, for semantic search)

### Quick Start

```bash
# Clone repository
git clone https://github.com/yourusername/error-agent.git
cd ErrorAgent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set OpenAI API key (optional)
export OPENAI_API_KEY=your-key-here

# Run UI
streamlit run src/ui/app_streamlit.py
```

### Development Installation

```bash
# Install with dev dependencies
pip install -e ".[dev,analysis,observability]"

# Run tests
pytest

# Format code
black src/
ruff check src/
```

## Usage

### Web UI

```bash
streamlit run src/ui/app_streamlit.py
```

Then:
1. Enter repository path
2. Select base/head commits (e.g., `HEAD~1` and `HEAD`)
3. Upload test results (pytest XML/JSON) and/or CI logs
4. Click "Run Analysis"
5. Review hypotheses and verification steps

### Python API

```python
from src.agent.schemas import AgentState
from src.agent.graph import DiagnosticAgent

# Create agent
agent = DiagnosticAgent()

# Define analysis
state = AgentState(
    repo_path="/path/to/repo",
    base_commit="HEAD~1",
    head_commit="HEAD",
    test_artifacts_path="test_results.xml",
    ci_logs_path="ci_logs.txt"
)

# Run analysis
report = agent.run(state)

# Access hypotheses
for hyp in report.hypotheses:
    print(f"#{hyp.rank}: {hyp.title} ({hyp.confidence:.0%})")
    print(f"  Change: {hyp.causal_chain.change}")
    print(f"  Usage: {hyp.causal_chain.usage}")
    print(f"  Break: {hyp.causal_chain.break_reason}")
    print(f"  Check: {hyp.causal_chain.first_check}")
```

## Example Output

```
🎯 Hypothesis #1: Modified user authentication breaks login tests (85%)

🔗 Causal Chain:
  What Changed: Modified auth.py::validate_token() - added expiration check
  Where Used: Used by login_handler() in api/routes.py:45
  Why It Broke: New expiration logic raises exception when token has no 'exp' claim,
                but test fixtures create tokens without expiration
  First Check: Verify test fixtures in tests/test_auth.py include 'exp' claim

✅ Verification Steps:
  1. Check auth.py::validate_token() for new exception types
  2. Review test fixtures in tests/test_auth.py
  3. Run: pytest tests/test_auth.py::test_login -v
  4. Add 'exp' claim to test token fixtures

📂 Files to Examine:
  - src/auth.py
  - src/api/routes.py
  - tests/test_auth.py
```

## Configuration

### Environment Variables

```bash
# Required for semantic search
export OPENAI_API_KEY=sk-...

# Optional: LangSmith tracing
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=ls__...

# Optional: Custom model
export OPENAI_MODEL=gpt-4o
```

### Supported Formats

**Test Reports:**
- pytest JUnit XML (`--junit-xml=report.xml`)
- pytest JSON (`--json-report --json-report-file=report.json`)

**CI Logs:**
- GitHub Actions logs
- GitLab CI logs
- Generic text logs with standard error patterns

**Coverage:**
- coverage.py JSON output (`coverage json`)

## How It Works

### Pipeline Steps

1. **Ingest Changes**: Parse git diffs, extract changed files and symbols
2. **Ingest Failures**: Parse test failures and CI errors
3. **Build Index**: Create call graph (AST) and vector embeddings
4. **Correlate**: Link code changes to failure locations via usage graph
5. **Generate Hypotheses**: Use LLM with structured output (Pydantic)
6. **Rank & Validate**: Score hypotheses by evidence overlap and specificity
7. **Finalize Report**: Organize top N hypotheses with action items

### Key Technologies

- **LangGraph**: Stateful agent workflow orchestration
- **LangChain**: LLM prompting and structured outputs
- **Pydantic**: Schema validation for hypothesis generation
- **NetworkX**: Call graph and dependency analysis
- **FAISS**: Vector similarity search for code
- **AST**: Static analysis of Python code
- **GitPython**: Git repository access
- **Streamlit**: Web UI

## Limitations

- **Language Support**: Currently optimized for Python (extensible to JS/TS)
- **LLM Required**: Needs OpenAI API for hypothesis generation (can use other LLMs)
- **Local Execution**: Processes code locally (privacy-friendly but no distributed compute)
- **Repository Size**: Large repos (>10K files) may be slow to index

## Roadmap

- [ ] Support for more languages (JavaScript, TypeScript, Java, Go)
- [ ] Local LLM support (Ollama, LlamaCpp)
- [ ] GitHub Actions integration
- [ ] VSCode extension
- [ ] Hypothesis caching and incremental analysis
- [ ] Interactive hypothesis refinement
- [ ] Team collaboration features

## Contributing

Contributions welcome! Areas of interest:
- Additional language support (parsers, AST analyzers)
- Alternative LLM backends
- UI improvements
- Ranking algorithm enhancements
- Documentation and examples

## License

MIT License - see LICENSE file

## Acknowledgments

Built with:
- [LangChain](https://python.langchain.com/) & [LangGraph](https://langchain-ai.github.io/langgraph/)
- [Streamlit](https://streamlit.io/)
- Research on code analysis and debugging agents

---

**Questions?** Open an issue or start a discussion!
