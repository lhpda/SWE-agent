# SWE Agent Developer Guide

**Version**: 1.0  
**Last Updated**: 2026-09-16

This guide provides technical documentation for developers working on the SWE Agent codebase. It covers system architecture, development workflows, and extension points.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Code Organization](#code-organization)
3. [Adding New Tools](#adding-new-tools)
4. [Adding Language Support](#adding-language-support)
5. [Testing Guidelines](#testing-guidelines)
6. [Development Workflow](#development-workflow)

---

## Architecture Overview

### System Components

SWE Agent follows a **multi-stage pipeline architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR LAYER                        │
│  • Pipeline state machine (state_machine.py)                │
│  • Stage transition logic (retry.py)                        │
│  • Error aggregation (error_handler.py)                     │
└────┬──────────┬──────────┬──────────┬─────────────────────┘
     │          │          │          │
     ↓          ↓          ↓          ↓
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│Localiza- │ │Reproduc- │ │  Patch   │ │Validation│
│  tion    │ │  tion    │ │   Gen    │ │          │
│  Agent   │ │  Agent   │ │  Agent   │ │  Agent   │
└────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
     │            │            │            │
     └────────────┴────────────┴────────────┘
                       ↓
     ┌──────────────────────────────────────┐
     │         CROSS-CUTTING LAYERS         │
     │  • Tool Layer (base.py, registry.py) │
     │  • Sandbox Layer (docker.py)         │
     │  • Storage Layer (storage.py)        │
     │  • LLM Integration (per agent)       │
     └──────────────────────────────────────┘
```

### Data Flow

1. **Input**: GitHub Issue + Repository Path
2. **Stage 1 - Localization**: Parse issue → Search codebase → Return candidate files
3. **Stage 2 - Reproduction**: Setup environment → Run tests → Confirm bug exists
4. **Stage 3 - Patch Generation**: Build context → Generate fixes → Validate syntax
5. **Stage 4 - Validation**: Apply patch → Run tests → Check for regressions
6. **Output**: Verified patch file + test results + execution logs

### Core Design Principles

1. **Stage Isolation**: Each agent has independent context and tools
2. **Structured Communication**: Stages exchange Pydantic-validated data structures
3. **Early Failure**: Validation at stage boundaries prevents error propagation
4. **Observability**: All decisions and intermediate results are logged
5. **Resource Limits**: Timeouts, retries, and quotas at every layer

---

## Code Organization

### Directory Structure

```
src/swe_agent/
├── __init__.py                  # Package initialization
├── types.py                     # Core Pydantic models (9 types)
├── config.py                    # Global configuration
├── logging.py                   # Structured logging setup
├── storage.py                   # State persistence
│
├── tools/                       # Tool Layer
│   ├── __init__.py
│   ├── base.py                  # Tool abstract base class
│   ├── registry.py              # Tool registration and discovery
│   ├── search.py                # ripgrep, symbol search, AST query
│   ├── file_ops.py              # read_file, apply_patch
│   ├── analysis.py              # syntax_check, parse_ast, get_imports
│   └── sandbox_exec.py          # run_command, run_test, install_deps
│
├── sandbox/                     # Sandbox Layer
│   ├── __init__.py
│   ├── docker.py                # Docker container management
│   ├── network.py               # Network isolation and whitelist
│   └── snapshot.py              # Container snapshots and rollback
│
├── agents/                      # Agent Layer
│   ├── localization/
│   │   ├── __init__.py
│   │   ├── parser.py            # Issue parsing
│   │   ├── strategy.py          # Search strategies
│   │   └── agent.py             # LocalizationAgent
│   │
│   ├── reproduction/
│   │   ├── __init__.py
│   │   ├── detector.py          # Project/test framework detection
│   │   ├── log_analyzer.py      # Error log parsing
│   │   └── agent.py             # ReproductionAgent
│   │
│   ├── patch/
│   │   ├── __init__.py
│   │   ├── edit_engine.py       # Code editing operations
│   │   ├── context_builder.py   # Context extraction
│   │   ├── generator.py         # Patch generation (beam search)
│   │   ├── validator.py         # Syntax validation
│   │   └── agent.py             # PatchGeneratorAgent
│   │
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── applicator.py        # Patch application
│   │   ├── test_runner.py       # Test execution
│   │   ├── regression.py        # Regression detection
│   │   └── agent.py             # ValidationAgent
│   │
│   └── verification/
│       ├── __init__.py
│       └── test_executor.py     # Multi-framework test executor
│
└── orchestrator/                # Orchestrator Layer
    ├── __init__.py
    ├── state_machine.py         # Pipeline state machine
    ├── retry.py                 # Retry and backoff logic
    └── error_handler.py         # Error classification and reporting
```

### Module Responsibilities

#### Core Modules

- **types.py**: Defines all Pydantic models for data validation and serialization
  - `IssueContext`, `RepositoryContext`
  - `LocalizationResult`, `ReproductionResult`, `PatchResult`, `ValidationResult`
  - `PipelineState`, `StageStatus`, `ErrorInfo`
  - `ToolCall`, `ToolResult`, `PipelineResult`

- **config.py**: Global configuration management
  - Environment variable loading
  - Timeout and resource limits
  - LLM API configuration

- **logging.py**: Structured logging (JSON Lines format)
  - Automatic session_id tracking
  - Context-aware log enrichment
  - Log level control

- **storage.py**: State persistence layer
  - Session management (`.swe-agent/sessions/{session_id}/`)
  - Stage result storage
  - FIFO cleanup policy (100 sessions max)
  - Thread-safe operations

#### Tool Layer

All tools extend the `Tool` abstract base class and provide:
- JSON Schema parameter validation
- Automatic output truncation (10KB default)
- Error handling and logging
- LLM-ready schema generation

Current tools:
- **Search**: `ripgrep_search`, `symbol_search`, `ast_query`
- **File Operations**: `read_file`, `read_file_with_context`, `apply_patch`
- **Code Analysis**: `syntax_check`, `parse_ast`, `get_imports`, `detect_project_type`
- **Sandbox Execution**: `run_command`, `run_test`, `install_deps`

#### Sandbox Layer

- **docker.py**: Container lifecycle management
  - Resource limits (2 CPU cores, 4GB RAM, 10GB disk)
  - Automatic cleanup (2-hour max lifetime)
  - File copying and command execution

- **network.py**: Network isolation
  - Custom Docker network with DNS filtering
  - Domain whitelist (PyPI, npm, Maven, etc.)
  - Request logging

- **snapshot.py**: State management
  - Container snapshots for rollback
  - Git stash integration
  - Automatic cleanup

#### Agent Layer

Each agent follows the same pattern:
1. **Input**: Structured data from previous stage
2. **Tool Selection**: Choose appropriate tools
3. **LLM Orchestration**: Claude API for decision-making
4. **Result Aggregation**: Structured output
5. **Validation**: Stage-specific checks

Agents are stateless and idempotent (given the same input, produce the same output).

#### Orchestrator Layer

- **state_machine.py**: Defines valid state transitions
  - States: IDLE → LOCALIZING → REPRODUCING → PATCHING → VALIDATING → DONE/FAILED
  - Persistent state storage
  - Resume from any stage

- **retry.py**: Retry policies
  - Per-stage retry limits
  - Exponential backoff
  - Dead loop detection (sliding window)
  - Circuit breaker pattern

- **error_handler.py**: Error management
  - Recoverable vs. non-recoverable classification
  - Error aggregation
  - Context preservation

---

## Adding New Tools

### Step 1: Define Tool Class

Create a new file in `src/swe_agent/tools/` or add to an existing file:

```python
from typing import Any, Dict
from swe_agent.tools.base import Tool, ToolResult

class MyTool(Tool):
    """Brief description of what this tool does."""

    name = "my_tool"
    description = "Detailed description for LLM consumption"
    parameters_schema = {
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "What param1 does"
            },
            "param2": {
                "type": "integer",
                "description": "What param2 does",
                "default": 10
            }
        },
        "required": ["param1"]
    }
    
    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool logic.
        
        Args:
            **kwargs: Validated parameters
            
        Returns:
            ToolResult with output or error
        """
        # 1. Validate parameters
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters"
            )
        
        # 2. Perform the work
        try:
            result = self._do_work(kwargs["param1"], kwargs.get("param2", 10))
            
            # 3. Truncate if needed
            return self.truncate_output(result)
            
        except Exception as e:
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Tool execution failed: {e}"
            )
    
    def _do_work(self, param1: str, param2: int) -> str:
        """Internal implementation."""
        # Your logic here
        return f"Result: {param1} * {param2}"
```

### Step 2: Register the Tool

In your tool module's `__init__.py` or at module level:

```python
from swe_agent.tools.registry import get_global_registry

# Register the tool
registry = get_global_registry()
registry.register(MyTool())
```

### Step 3: Add Tests

Create `tests/test_my_tool.py`:

```python
import pytest
from swe_agent.tools.my_module import MyTool

def test_my_tool_valid_input():
    """Test tool with valid input."""
    tool = MyTool()
    result = tool.execute(param1="test", param2=5)
    
    assert result.error is None
    assert result.truncated is False
    assert "Result: test * 5" in result.output

def test_my_tool_invalid_params():
    """Test tool with invalid parameters."""
    tool = MyTool()
    result = tool.execute()  # Missing required param1
    
    assert result.error is not None

def test_my_tool_output_truncation():
    """Test output truncation for large results."""
    tool = MyTool()
    tool.max_output_size = 100  # Set small limit
    
    large_param = "x" * 1000
    result = tool.execute(param1=large_param)
    
    assert result.truncated is True
```

### Step 4: Document the Tool

Add to this file under "Current tools" section and create examples in `docs/EXAMPLES.md`.

### Best Practices

- **Single Responsibility**: Each tool does one thing well
- **Idempotent**: Same input → same output (no hidden state)
- **Descriptive Schemas**: LLM needs clear parameter descriptions
- **Error Handling**: Return `ToolResult` with clear error messages
- **Resource Limits**: Respect timeout and size limits
- **Logging**: Use structured logging for debugging

---

## Adding Language Support

SWE Agent currently supports Python, JavaScript, Java, and Rust. To add a new language:

### Step 1: Update Project Detection

Edit `src/swe_agent/agents/reproduction/detector.py`:

```python
def detect_project_type(repo_path: str) -> str:
    """Detect project type from repository structure."""
    
    # Add your language indicators
    if (repo_path / "Cargo.toml").exists():
        return "rust"
    elif (repo_path / "go.mod").exists():
        return "go"  # New language
    # ... existing checks
```

### Step 2: Add Syntax Checker

Edit `src/swe_agent/tools/analysis.py`:

```python
def _check_go_syntax(code: str) -> ToolResult:
    """Check Go syntax using gofmt."""
    try:
        result = subprocess.run(
            ["gofmt", "-e"],
            input=code,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return ToolResult(
                output=None,
                truncated=False,
                error=result.stderr
            )
        
        return ToolResult(output="Syntax valid", truncated=False)
    except Exception as e:
        return ToolResult(output=None, truncated=False, error=str(e))
```

Update the `syntax_check` tool to route to your checker:

```python
def execute(self, **kwargs: Any) -> ToolResult:
    language = kwargs["language"]
    code = kwargs["code"]
    
    checkers = {
        "python": _check_python_syntax,
        "javascript": _check_js_syntax,
        "go": _check_go_syntax,  # Add here
    }
    
    checker = checkers.get(language)
    if not checker:
        return ToolResult(
            output=None,
            truncated=False,
            error=f"Unsupported language: {language}"
        )
    
    return checker(code)
```

### Step 3: Add Test Framework Support

Edit `src/swe_agent/agents/reproduction/detector.py`:

```python
def detect_test_framework(repo_path: str, project_type: str) -> Optional[str]:
    """Detect test framework for a project."""
    
    if project_type == "go":
        # Go has built-in testing
        if any((repo_path).rglob("*_test.go")):
            return "go_test"
    # ... existing frameworks
```

Edit `src/swe_agent/tools/sandbox_exec.py` to add test runner:

```python
def _run_go_test(self, test_path: str) -> str:
    """Run Go tests."""
    cmd = f"cd {test_path} && go test -v ./..."
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=self.test_timeout
    )
    return result.stdout + result.stderr
```

### Step 4: Add AST Parsing (Optional)

If tree-sitter supports your language, add parser configuration:

```python
# In tools/analysis.py
LANGUAGE_PARSERS = {
    "python": tree_sitter.Language('build/languages.so', 'python'),
    "javascript": tree_sitter.Language('build/languages.so', 'javascript'),
    "go": tree_sitter.Language('build/languages.so', 'go'),  # Add here
}
```

### Step 5: Add Tests

Create language-specific test files:

```python
# tests/test_go_support.py

def test_detect_go_project(tmp_path):
    """Test Go project detection."""
    (tmp_path / "go.mod").write_text("module example.com/myapp\n")
    
    project_type = detect_project_type(tmp_path)
    assert project_type == "go"

def test_go_syntax_check():
    """Test Go syntax validation."""
    valid_code = 'package main\n\nfunc main() {}\n'
    tool = SyntaxCheckTool()
    
    result = tool.execute(language="go", code=valid_code)
    assert result.error is None
```

### Step 6: Update Documentation

- Add language to README.md supported languages list
- Add examples to `docs/EXAMPLES.md`
- Update this section with language-specific details

---

## Testing Guidelines

### Test Organization

```
tests/
├── unit/                        # Unit tests (fast, isolated)
│   ├── test_types.py
│   ├── test_storage.py
│   ├── test_tools_*.py
│   └── test_agents_*.py
│
├── integration/                 # Integration tests (slower, external deps)
│   ├── test_localization_e2e.py
│   ├── test_reproduction_e2e.py
│   └── test_docker_sandbox.py
│
├── e2e/                        # End-to-end tests (full pipeline)
│   ├── test_simple_bugs.py
│   ├── test_complex_bugs.py
│   └── test_negative_cases.py
│
└── fixtures/                   # Test data
    ├── repos/                  # Sample repositories
    ├── issues/                 # Issue JSON files
    └── patches/                # Expected patches
```

### Testing Principles

1. **Test Pyramid**: Many unit tests, fewer integration tests, minimal E2E tests
2. **Isolation**: Mock external dependencies (LLM, Docker in unit tests)
3. **TDD**: Write tests before implementation when possible
4. **Coverage**: Maintain >80% code coverage
5. **Fast Feedback**: Unit tests should run in <5 seconds total

### Writing Tests

#### Unit Test Example

```python
import pytest
from unittest.mock import Mock, patch
from swe_agent.tools.search import RipgrepSearchTool

def test_ripgrep_search_valid_pattern(tmp_path):
    """Test ripgrep search with valid pattern."""
    # Setup
    test_file = tmp_path / "test.py"
    test_file.write_text("def foo():\n    pass\n")
    
    tool = RipgrepSearchTool()
    
    # Execute
    result = tool.execute(
        pattern="def foo",
        path=str(tmp_path)
    )
    
    # Assert
    assert result.error is None
    assert "test.py" in result.output
    assert result.truncated is False

@patch('subprocess.run')
def test_ripgrep_timeout(mock_run, tmp_path):
    """Test ripgrep handles timeout gracefully."""
    mock_run.side_effect = subprocess.TimeoutExpired('rg', 5)
    
    tool = RipgrepSearchTool()
    result = tool.execute(pattern="test", path=str(tmp_path))
    
    assert result.error is not None
    assert "timeout" in result.error.lower()
```

#### Integration Test Example

```python
import pytest
from swe_agent.agents.localization.agent import LocalizationAgent
from swe_agent.types import IssueContext, RepositoryContext

@pytest.mark.integration
def test_localization_agent_with_stack_trace(test_repo):
    """Test localization with clear stack trace."""
    # Setup real repository fixture
    issue = IssueContext(
        issue_id="TEST-001",
        title="IndexError in data processing",
        body="```\nTraceback:\n  File 'processor.py', line 42\n    IndexError\n```",
        parsed={"error_type": "IndexError"},
        metadata={}
    )
    
    repo = RepositoryContext(
        path=str(test_repo),
        git={"branch": "main"},
        project_type="python",
        test_framework="pytest",
        dependencies={}
    )
    
    # Execute (with real tools, mocked LLM)
    agent = LocalizationAgent(llm_api_key="mock")
    with patch.object(agent, '_call_llm') as mock_llm:
        mock_llm.return_value = {
            "tool_calls": [
                {"tool": "ripgrep_search", "args": {"pattern": "IndexError"}}
            ]
        }
        
        result = agent.localize(issue, repo)
    
    # Assert
    assert result.status == "success"
    assert len(result.candidates) > 0
    assert result.candidates[0]["file"].endswith("processor.py")
```

#### E2E Test Example

```python
@pytest.mark.e2e
@pytest.mark.slow
def test_full_pipeline_simple_bug():
    """Test complete pipeline on a simple bug fix."""
    # This test runs the full pipeline with real Docker, LLM, etc.
    # Skip in CI if Docker not available
    
    issue_url = "https://github.com/example/repo/issues/123"
    repo_path = "tests/fixtures/repos/simple-python-bug"
    
    from swe_agent.orchestrator.pipeline import PipelineOrchestrator
    
    orchestrator = PipelineOrchestrator(
        issue_url=issue_url,
        repo_path=repo_path
    )
    
    result = orchestrator.run()
    
    assert result.status == "success"
    assert result.patch is not None
    assert result.validation_result.tests_passed > 0
```

### Mocking Guidelines

- **Mock LLM calls**: Always mock in unit/integration tests
- **Mock Docker**: Use `pytest-docker` fixtures or mock in unit tests
- **Mock filesystem**: Use `tmp_path` fixture for temporary directories
- **Mock subprocess**: Use `unittest.mock.patch` for external commands

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run only unit tests (fast)
poetry run pytest tests/unit/

# Run with coverage
poetry run pytest --cov=src/swe_agent --cov-report=html

# Run specific test
poetry run pytest tests/unit/test_storage.py::test_save_stage_result

# Run integration tests (requires Docker)
poetry run pytest tests/integration/ -v

# Skip slow tests
poetry run pytest -m "not slow"
```

### Test Markers

```python
@pytest.mark.unit          # Fast, isolated unit test
@pytest.mark.integration   # Integration test with external deps
@pytest.mark.e2e           # Full pipeline test
@pytest.mark.slow          # Takes >10 seconds
@pytest.mark.requires_docker  # Needs Docker daemon
@pytest.mark.requires_llm  # Needs LLM API key
```

### Coverage Requirements

- **New code**: 100% coverage required
- **Modified code**: Cannot decrease overall coverage
- **Overall project**: Maintain >80% coverage
- **Critical paths**: 100% coverage (state machine, retry logic, error handling)

---

## Development Workflow

### Initial Setup

```bash
# Clone repository
git clone https://github.com/yourusername/swe-agent.git
cd swe-agent

# Install dependencies
poetry install

# Setup pre-commit hooks
poetry run pre-commit install

# Run tests to verify setup
poetry run pytest tests/unit/
```

### Development Cycle

1. **Create a branch**
   ```bash
   git checkout -b feature/add-go-support
   ```

2. **Write tests first (TDD)**
   ```bash
   # Write failing test
   vim tests/test_go_support.py
   poetry run pytest tests/test_go_support.py  # Should fail
   ```

3. **Implement feature**
   ```bash
   vim src/swe_agent/tools/analysis.py
   poetry run pytest tests/test_go_support.py  # Should pass
   ```

4. **Run full test suite**
   ```bash
   poetry run pytest
   poetry run black .
   poetry run ruff check .
   poetry run mypy src/
   ```

5. **Commit and push**
   ```bash
   git add .
   git commit -m "feat: add Go language support"
   git push origin feature/add-go-support
   ```

6. **Create pull request** (see CONTRIBUTING.md)

### Code Quality Tools

- **black**: Code formatting (line length 88)
- **ruff**: Fast linting (replaces flake8, isort, etc.)
- **mypy**: Static type checking
- **pytest**: Testing framework
- **pre-commit**: Automatic checks on commit

### Debugging Tips

1. **Enable debug logging**
   ```python
   import os
   os.environ["SWE_AGENT_LOG_LEVEL"] = "DEBUG"
   ```

2. **Use pytest debugging**
   ```bash
   # Drop into debugger on failure
   poetry run pytest --pdb
   
   # Show print statements
   poetry run pytest -s
   
   # Run specific test with verbose output
   poetry run pytest tests/test_foo.py::test_bar -vv
   ```

3. **Inspect Docker containers**
   ```bash
   # List all containers (including stopped)
   docker ps -a | grep swe-agent
   
   # Inspect container logs
   docker logs <container_id>
   
   # Exec into running container
   docker exec -it <container_id> /bin/bash
   ```

4. **Check session state**
   ```bash
   # Session files are in .swe-agent/sessions/
   ls -la .swe-agent/sessions/<session_id>/
   cat .swe-agent/sessions/<session_id>/state.json
   ```

### Performance Profiling

```python
# Add to your test
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Code to profile
agent.localize(issue, repo)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

---

## Additional Resources

- **SYSTEM_DESIGN.md**: Complete system architecture specification
- **CONTRIBUTING.md**: Contribution guidelines and PR process
- **API_REFERENCE.md**: (Future) Generated API documentation
- **EXAMPLES.md**: (Future) Usage examples and tutorials

For questions or discussions, open an issue on GitHub or join our community chat.
