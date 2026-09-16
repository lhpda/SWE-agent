# Contributing to SWE Agent

Thank you for your interest in contributing to SWE Agent! This document provides guidelines and instructions for contributing to the project.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Setup](#development-setup)
3. [Code Style Guidelines](#code-style-guidelines)
4. [Testing Requirements](#testing-requirements)
5. [Pull Request Process](#pull-request-process)
6. [Documentation Requirements](#documentation-requirements)
7. [Community Guidelines](#community-guidelines)

---

## Getting Started

### Prerequisites

Before contributing, ensure you have:

- **Python 3.11+** installed
- **Poetry** for dependency management (`pip install poetry`)
- **Docker** for sandbox testing (optional for unit tests)
- **Git** for version control
- An **Anthropic API key** for integration tests (optional)

### First Steps

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/swe-agent.git
   cd swe-agent
   ```

3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/original/swe-agent.git
   ```

4. **Install dependencies**:
   ```bash
   poetry install
   ```

5. **Verify setup**:
   ```bash
   poetry run pytest tests/unit/
   ```

### Finding Work

- Check **Issues** labeled `good first issue` or `help wanted`
- Review **TASKS.md** for planned features
- Propose new features by opening an issue first
- Ask questions in issues or discussions before starting large changes

---

## Development Setup

### Environment Configuration

Create a `.env` file (not committed to Git):

```bash
# Optional: LLM API key for integration tests
ANTHROPIC_API_KEY=sk-...

# Optional: Override default configuration
SWE_AGENT_LOG_LEVEL=DEBUG
SWE_AGENT_MAX_SESSIONS=50
```

### Pre-commit Hooks

Install pre-commit hooks to automatically check code quality:

```bash
poetry run pre-commit install
```

This will run `black`, `ruff`, and `mypy` on every commit.

### Development Tools

We use the following tools (all configured in `pyproject.toml`):

- **black**: Code formatter (line length 88)
- **ruff**: Fast Python linter
- **mypy**: Static type checker
- **pytest**: Testing framework
- **pytest-cov**: Code coverage reporting

### IDE Setup

#### VS Code

Recommended extensions:
- Python (Microsoft)
- Pylance
- Ruff
- mypy

Recommended settings (`.vscode/settings.json`):
```json
{
  "python.formatting.provider": "black",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.linting.mypyEnabled": true,
  "editor.formatOnSave": true
}
```

#### PyCharm

- Enable Black as external tool
- Configure mypy as external tool
- Set import optimization to use ruff

---

## Code Style Guidelines

### Python Style

We follow **PEP 8** with modifications enforced by Black:

- **Line length**: 88 characters (Black default)
- **Indentation**: 4 spaces
- **Quotes**: Double quotes preferred
- **Imports**: Sorted by ruff (compatible with isort)

### Type Hints

**All functions must have type hints**:

```python
# Good
def process_file(path: str, max_size: int = 1024) -> dict[str, Any]:
    """Process a file and return metadata."""
    ...

# Bad - missing type hints
def process_file(path, max_size=1024):
    ...
```

Use modern type syntax (Python 3.11+):
- `list[str]` instead of `List[str]`
- `dict[str, int]` instead of `Dict[str, int]`
- `str | None` instead of `Optional[str]`

### Docstrings

Use **Google-style docstrings** for all public functions and classes:

```python
def execute_tool(tool_name: str, params: dict[str, Any]) -> ToolResult:
    """Execute a registered tool with given parameters.
    
    This function validates parameters, executes the tool, and returns
    the result with appropriate error handling.
    
    Args:
        tool_name: Name of the tool to execute
        params: Dictionary of parameters to pass to the tool
        
    Returns:
        ToolResult containing output or error information
        
    Raises:
        ValueError: If tool is not registered
        ToolExecutionError: If tool execution fails
        
    Example:
        >>> result = execute_tool("ripgrep_search", {"pattern": "TODO"})
        >>> print(result.output)
    """
    ...
```

### Naming Conventions

- **Variables/functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private members**: `_leading_underscore`
- **Type aliases**: `PascalCase`

```python
# Good
class LocalizationAgent:
    MAX_RETRIES = 3
    
    def __init__(self, config: AgentConfig) -> None:
        self._llm_client = None
        
    def localize(self, issue: IssueContext) -> LocalizationResult:
        return self._perform_search(issue)
        
    def _perform_search(self, issue: IssueContext) -> LocalizationResult:
        ...
```

### Import Organization

Imports should be organized in three groups:

1. Standard library
2. Third-party libraries
3. Local modules

```python
# Standard library
import os
import sys
from pathlib import Path
from typing import Any

# Third-party
import docker
from pydantic import BaseModel

# Local
from swe_agent.logging import get_logger
from swe_agent.tools.base import Tool
from swe_agent.types import ToolResult
```

### Error Handling

- Use **specific exceptions**, not bare `except:`
- Provide **clear error messages**
- Log errors with **structured logging**

```python
# Good
try:
    result = subprocess.run(cmd, capture_output=True, timeout=30)
except subprocess.TimeoutExpired:
    logger.error("command_timeout", cmd=cmd, timeout=30)
    raise ToolExecutionError(f"Command timed out after 30s: {cmd}")
except FileNotFoundError:
    logger.error("command_not_found", cmd=cmd)
    raise ToolExecutionError(f"Command not found: {cmd}")

# Bad
try:
    result = subprocess.run(cmd)
except:
    print("Error!")
    return None
```

### Logging

Use structured logging, never print statements:

```python
from swe_agent.logging import get_logger

logger = get_logger(__name__)

# Good
logger.info("tool_executed", tool=tool_name, duration=elapsed_time)
logger.error("tool_failed", tool=tool_name, error=str(e))

# Bad
print(f"Tool {tool_name} executed in {elapsed_time}s")
```

### Code Organization

- **Keep functions small**: Aim for <50 lines
- **Single responsibility**: One function, one job
- **Avoid deep nesting**: Extract complex logic into helper functions
- **Use early returns**: Avoid deep if-else chains

```python
# Good
def validate_and_execute(tool: Tool, params: dict) -> ToolResult:
    if not tool.validate_parameters(params):
        return ToolResult(output=None, truncated=False, error="Invalid params")
    
    if not self._check_permissions(tool):
        return ToolResult(output=None, truncated=False, error="Permission denied")
    
    return tool.execute(**params)

# Bad - deep nesting
def validate_and_execute(tool: Tool, params: dict) -> ToolResult:
    if tool.validate_parameters(params):
        if self._check_permissions(tool):
            return tool.execute(**params)
        else:
            return ToolResult(output=None, truncated=False, error="Permission denied")
    else:
        return ToolResult(output=None, truncated=False, error="Invalid params")
```

---

## Testing Requirements

### Test Coverage

- **New code**: Must have >90% test coverage
- **Modified code**: Cannot decrease overall project coverage
- **Critical paths**: Must have 100% coverage (state machine, retry logic, error handling)
- **Overall project**: Must maintain >80% coverage

### Test Structure

Every module should have corresponding tests:

```
src/swe_agent/tools/search.py  →  tests/unit/test_tools_search.py
src/swe_agent/agents/patch/agent.py  →  tests/unit/test_patch_agent.py
```

### Test Types

#### 1. Unit Tests (Required)

- **Fast** (<5 seconds for full suite)
- **Isolated** (mock external dependencies)
- **Focused** (test one function/class)

```python
def test_tool_parameter_validation():
    """Test that invalid parameters are rejected."""
    tool = RipgrepSearchTool()
    result = tool.execute(pattern="", path="/nonexistent")
    
    assert result.error is not None
    assert "pattern" in result.error.lower()
```

#### 2. Integration Tests (Encouraged)

- Test interactions between components
- Use real dependencies where practical
- Mock expensive operations (LLM calls)

```python
@pytest.mark.integration
def test_localization_with_real_repo(tmp_path):
    """Test localization agent on a real repository."""
    # Setup actual git repo
    repo = setup_test_repo(tmp_path)
    
    agent = LocalizationAgent(api_key="mock")
    with patch.object(agent, '_call_llm') as mock_llm:
        mock_llm.return_value = {"tool_calls": [...]}
        result = agent.localize(issue, repo)
    
    assert result.status == "success"
```

#### 3. E2E Tests (Optional)

- Full pipeline tests
- Run in CI but can be slow
- Mark with `@pytest.mark.e2e` and `@pytest.mark.slow`

### Test Naming

- Test files: `test_<module_name>.py`
- Test functions: `test_<what_it_tests>_<scenario>`

```python
def test_ripgrep_search_valid_pattern()  # Good
def test_ripgrep_timeout()              # Good
def test_error_case()                   # Bad - too vague
def test_1()                            # Bad - meaningless
```

### Fixtures

Use pytest fixtures for common setup:

```python
@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary git repository."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path)
    return repo_path

def test_something(temp_repo):
    """Test uses the fixture."""
    assert (temp_repo / ".git").exists()
```

### Running Tests

Before submitting a PR, run:

```bash
# Run all tests with coverage
poetry run pytest --cov=src/swe_agent --cov-report=term-missing

# Run specific test file
poetry run pytest tests/unit/test_storage.py -v

# Run tests matching pattern
poetry run pytest -k "test_tool" -v

# Run with verbose output
poetry run pytest -vv

# Skip slow tests
poetry run pytest -m "not slow"
```

### Test Requirements Checklist

- [ ] All new functions have unit tests
- [ ] Edge cases are tested (empty input, None, max values)
- [ ] Error conditions are tested
- [ ] Coverage is >90% for new code
- [ ] Tests pass locally: `poetry run pytest`
- [ ] Tests are fast (<1s per test for unit tests)

---

## Pull Request Process

### Branch Naming

Use descriptive branch names with prefixes:

- `feature/add-go-support` - New features
- `fix/handle-timeout-error` - Bug fixes
- `docs/update-contributing` - Documentation
- `refactor/simplify-registry` - Code refactoring
- `test/add-integration-tests` - Test additions

### Commit Messages

Follow **Conventional Commits** format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Build/tooling changes

**Examples**:

```bash
# Good commits
git commit -m "feat(tools): add Go syntax checker"
git commit -m "fix(sandbox): handle container timeout gracefully"
git commit -m "docs: add language support guide to DEVELOPER.md"

# Bad commits
git commit -m "fixed bug"
git commit -m "updates"
git commit -m "WIP"
```

### Before Submitting PR

1. **Sync with upstream**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run all checks**:
   ```bash
   # Format code
   poetry run black .
   
   # Lint
   poetry run ruff check . --fix
   
   # Type check
   poetry run mypy src/
   
   # Run tests with coverage
   poetry run pytest --cov=src/swe_agent
   ```

3. **Update documentation** if needed
4. **Add entry to CHANGELOG.md** (if applicable)

### PR Template

When opening a PR, include:

```markdown
## Description
Brief description of what this PR does.

## Related Issue
Closes #123

## Changes Made
- Added Go language support
- Updated syntax checker to handle Go files
- Added integration tests

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] All tests pass locally
- [ ] Code coverage maintained/improved

## Documentation
- [ ] Updated DEVELOPER.md
- [ ] Updated CONTRIBUTING.md (if process changed)
- [ ] Added docstrings to new functions
- [ ] Updated CHANGELOG.md

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] No unnecessary changes included
```

### Review Process

1. **Automated checks** must pass (CI/CD)
2. **At least one maintainer approval** required
3. **Address review comments** promptly
4. **Squash commits** if requested
5. **Keep PR focused** - one feature/fix per PR

### What Reviewers Look For

- **Correctness**: Does it work? Are edge cases handled?
- **Tests**: Adequate test coverage?
- **Code quality**: Readable, maintainable, follows guidelines?
- **Documentation**: Docstrings, comments where needed?
- **Impact**: Does it break existing functionality?

### After PR is Merged

1. **Delete your branch**:
   ```bash
   git branch -d feature/my-feature
   ```

2. **Update your fork**:
   ```bash
   git checkout main
   git pull upstream main
   git push origin main
   ```

3. **Celebrate!** 🎉

---

## Documentation Requirements

### Code Documentation

Every public API must have:

1. **Docstring** with Google-style format
2. **Type hints** for all parameters and return values
3. **Examples** for complex functions

```python
def complex_function(
    param1: str,
    param2: int,
    param3: dict[str, Any] | None = None
) -> tuple[bool, str]:
    """Brief one-line description.
    
    Longer description explaining what the function does, its purpose,
    and any important details users should know.
    
    Args:
        param1: Description of param1
        param2: Description of param2
        param3: Optional parameter description. Defaults to None.
        
    Returns:
        Tuple of (success, message) where success indicates if the
        operation completed successfully.
        
    Raises:
        ValueError: If param2 is negative
        RuntimeError: If operation fails
        
    Example:
        >>> success, msg = complex_function("test", 42)
        >>> print(success)
        True
    """
    ...
```

### User-Facing Documentation

When adding features, update:

- **README.md**: If it affects installation or basic usage
- **docs/USER_GUIDE.md**: For user-facing features
- **docs/DEVELOPER.md**: For developer-facing changes
- **docs/EXAMPLES.md**: Add usage examples

### Documentation Style

- Use **clear, concise language**
- Include **code examples** where helpful
- Use **bullet points** for lists
- Use **tables** for comparisons
- Include **diagrams** for complex concepts (ASCII art is fine)

---

## Community Guidelines

### Code of Conduct

We are committed to providing a welcoming and inclusive environment. All contributors must:

- Be respectful and professional
- Accept constructive criticism gracefully
- Focus on what is best for the community
- Show empathy towards others

### Communication Channels

- **GitHub Issues**: Bug reports, feature requests
- **GitHub Discussions**: Questions, ideas, general discussion
- **Pull Requests**: Code contributions

### Getting Help

- **Read documentation first**: DEVELOPER.md, SYSTEM_DESIGN.md
- **Search existing issues**: Your question may be answered
- **Ask in discussions**: For general questions
- **Open an issue**: For specific bugs or features

### Recognition

Contributors will be:

- Listed in **CONTRIBUTORS.md**
- Mentioned in **release notes**
- Credited in commits (Co-Authored-By)

---

## Quick Reference

### Common Tasks

```bash
# Setup
poetry install
poetry run pre-commit install

# Development
poetry run pytest tests/unit/           # Run unit tests
poetry run pytest --cov=src/swe_agent  # Run with coverage
poetry run black .                      # Format code
poetry run ruff check . --fix          # Lint and fix
poetry run mypy src/                   # Type check

# Before PR
git fetch upstream
git rebase upstream/main
poetry run pytest
poetry run black .
poetry run ruff check .
poetry run mypy src/

# Debugging
poetry run pytest --pdb               # Drop to debugger on failure
poetry run pytest -s                  # Show print statements
poetry run pytest -vv                 # Verbose output
```

### Need Help?

- Review **DEVELOPER.md** for architecture details
- Check **TASKS.md** for current work items
- Open an issue with the `question` label
- Ask in GitHub Discussions

---

Thank you for contributing to SWE Agent! Every contribution, no matter how small, helps make the project better.
