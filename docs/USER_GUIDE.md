# SWE Agent User Guide

**Version**: 0.1.0  
**Last Updated**: 2026-09-16

---

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Configuration](#configuration)
5. [Usage](#usage)
6. [Troubleshooting](#troubleshooting)
7. [FAQ](#faq)

---

## Introduction

SWE Agent is an automated software engineering agent that helps fix bugs in your codebase. It takes a GitHub issue as input and automatically:

1. **Localizes** the bug by analyzing code and issue descriptions
2. **Reproduces** the error in an isolated sandbox environment
3. **Generates** minimal patches to fix the issue
4. **Validates** fixes without breaking existing tests

### Key Features

- **Automated Bug Fixing**: End-to-end pipeline from issue to patch
- **Sandboxed Execution**: Safe isolated Docker containers with resource limits
- **Multi-Language Support**: Python, JavaScript, Java, Rust
- **Intelligent Localization**: Uses stack traces, error messages, and code analysis
- **Validation**: Ensures fixes don't introduce regressions

---

## Installation

### Prerequisites

Before installing SWE Agent, ensure you have:

- **Python 3.11 or higher**
- **Docker** (for sandboxed execution)
- **Poetry** (for dependency management)
- **Git** (for repository management)

### System Requirements

- **CPU**: 2+ cores recommended
- **Memory**: 8GB+ RAM (4GB allocated to Docker containers)
- **Disk**: 10GB+ free space
- **OS**: Linux, macOS, or Windows with WSL2

### Step 1: Install Docker

#### Linux

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install docker.io docker-compose
sudo systemctl start docker
sudo systemctl enable docker

# Add your user to docker group (logout/login required)
sudo usermod -aG docker $USER
```

#### macOS

Download and install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop)

#### Windows

Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop) with WSL2 backend.

**Verify Docker installation:**

```bash
docker --version
docker run hello-world
```

### Step 2: Install Poetry

```bash
# Linux/macOS/WSL
curl -sSL https://install.python-poetry.org | python3 -

# Add to PATH (add to ~/.bashrc or ~/.zshrc)
export PATH="$HOME/.local/bin:$PATH"

# Verify installation
poetry --version
```

### Step 3: Clone and Install SWE Agent

```bash
# Clone the repository
git clone https://github.com/yourusername/swe-agent.git
cd swe-agent

# Install dependencies
poetry install

# Verify installation
poetry run python -c "import swe_agent; print(swe_agent.__version__)"
```

### Step 4: Set Up API Keys

SWE Agent uses Anthropic's Claude API for LLM capabilities.

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY="your-api-key-here"

# Or add to ~/.bashrc or ~/.zshrc for persistence
echo 'export ANTHROPIC_API_KEY="your-api-key-here"' >> ~/.bashrc
```

Get your API key from: https://console.anthropic.com/

### Verification

Run all checks to ensure proper installation:

```bash
# Check Python version
poetry run python --version  # Should be 3.11+

# Check Docker
docker ps  # Should list running containers (may be empty)

# Run tests (optional)
poetry run pytest tests/ -v

# Check configuration
poetry run python -c "from swe_agent.config import load_config; print(load_config())"
```

**Expected installation time**: 5-10 minutes

---

## Quick Start

### Your First Bug Fix

Let's fix a simple bug using SWE Agent.

#### Step 1: Prepare Your Repository

```bash
# Clone or navigate to a repository with a known issue
cd /path/to/your/repo

# Ensure the repository is a git repository
git status
```

#### Step 2: Run SWE Agent

```bash
# Basic usage
poetry run swe-agent \
  --issue "https://github.com/owner/repo/issues/123" \
  --repo /path/to/your/repo

# Or using issue number (if in the same repository)
poetry run swe-agent --issue 123 --repo .
```

#### Step 3: Monitor Progress

SWE Agent will display real-time progress:

```
[2026-09-16 10:00:00] Starting SWE Agent...
[2026-09-16 10:00:01] Session ID: abc123def456
[2026-09-16 10:00:02] Stage 1/4: Localization
[2026-09-16 10:02:15] ✓ Found 3 candidate files
[2026-09-16 10:02:16] Stage 2/4: Reproduction
[2026-09-16 10:05:30] ✓ Error reproduced successfully
[2026-09-16 10:05:31] Stage 3/4: Patch Generation
[2026-09-16 10:08:45] ✓ Generated 3 patch candidates
[2026-09-16 10:08:46] Stage 4/4: Validation
[2026-09-16 10:12:30] ✓ Patch validated successfully
[2026-09-16 10:12:31] Success! Patch saved to: .swe-agent/sessions/abc123def456/final_patch.diff
```

#### Step 4: Apply the Patch

```bash
# Review the generated patch
cat .swe-agent/sessions/abc123def456/final_patch.diff

# Apply the patch to your repository
git apply .swe-agent/sessions/abc123def456/final_patch.diff

# Verify the fix
git diff

# Run tests to confirm
pytest  # or your test command
```

### Resume a Session

If a session is interrupted, you can resume it:

```bash
poetry run swe-agent --resume abc123def456
```

---

## Configuration

SWE Agent can be configured through environment variables, configuration files, or command-line arguments.

### Configuration Priority

1. Command-line arguments (highest priority)
2. Environment variables
3. Configuration file
4. Default values (lowest priority)

### Environment Variables

All configuration can be set via environment variables with the prefix `SWE_AGENT_`:

#### Timeout Configuration

```bash
# Localization stage timeout (default: 300 seconds)
export SWE_AGENT_LOCALIZATION_TIMEOUT=300

# Reproduction stage timeout (default: 480 seconds)
export SWE_AGENT_REPRODUCTION_TIMEOUT=480

# Patch generation timeout (default: 360 seconds)
export SWE_AGENT_PATCH_GENERATION_TIMEOUT=360

# Validation timeout (default: 600 seconds)
export SWE_AGENT_VALIDATION_TIMEOUT=600

# Global pipeline timeout (default: 1800 seconds / 30 minutes)
export SWE_AGENT_GLOBAL_TIMEOUT=1800
```

#### Retry Configuration

```bash
# Maximum retries for localization (default: 3)
export SWE_AGENT_LOCALIZATION_MAX_RETRIES=3

# Maximum retries for reproduction (default: 5)
export SWE_AGENT_REPRODUCTION_MAX_RETRIES=5

# Maximum patch candidates in beam search (default: 5)
export SWE_AGENT_PATCH_MAX_RETRIES=5

# Maximum retries for validation (default: 1)
export SWE_AGENT_VALIDATION_MAX_RETRIES=1
```

#### Docker Resource Limits

```bash
# CPU cores allocated to Docker (default: 2)
export SWE_AGENT_DOCKER_CPU_LIMIT=2

# Memory limit for Docker (default: "4g")
export SWE_AGENT_DOCKER_MEMORY_LIMIT="4g"

# Docker command timeout (default: 600 seconds)
export SWE_AGENT_DOCKER_TIMEOUT=600
```

#### Storage Configuration

```bash
# Base path for session storage (default: ".swe-agent")
export SWE_AGENT_STORAGE_BASE_PATH=".swe-agent"

# Maximum size per session (default: 1GB)
export SWE_AGENT_MAX_SESSION_SIZE=1073741824

# Maximum number of sessions to keep (default: 100)
export SWE_AGENT_MAX_SESSIONS=100
```

#### Logging Configuration

```bash
# Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)
export SWE_AGENT_LOG_LEVEL="INFO"

# Log format: json or console (default: json)
export SWE_AGENT_LOG_FORMAT="json"
```

#### LLM Configuration

```bash
# Claude model to use (default: claude-sonnet-4-20250514)
export SWE_AGENT_LLM_MODEL="claude-sonnet-4-20250514"

# Maximum tokens per LLM request (default: 4096)
export SWE_AGENT_LLM_MAX_TOKENS=4096

# LLM temperature (default: 0.0)
export SWE_AGENT_LLM_TEMPERATURE=0.0
```

#### Output Limits

```bash
# Maximum tool output size (default: 10KB)
export SWE_AGENT_MAX_TOOL_OUTPUT_SIZE=10240

# Maximum test output size (default: 5KB)
export SWE_AGENT_MAX_TEST_OUTPUT_SIZE=5120

# Maximum file content size (default: 50000 characters)
export SWE_AGENT_MAX_FILE_SIZE=50000

# Maximum search results (default: 100)
export SWE_AGENT_MAX_SEARCH_RESULTS=100
```

### Configuration File

Create a `swe-agent.toml` file in your project root:

```toml
[swe_agent]
localization_timeout = 300
reproduction_timeout = 480
patch_generation_timeout = 360
validation_timeout = 600
global_timeout = 1800

max_retries = 3
localization_max_retries = 3
reproduction_max_retries = 5
patch_max_retries = 5
validation_max_retries = 1

docker_cpu_limit = 2
docker_memory_limit = "4g"
docker_timeout = 600

storage_base_path = ".swe-agent"
max_session_size = 1073741824
max_sessions = 100

log_level = "INFO"
log_format = "json"

llm_model = "claude-sonnet-4-20250514"
llm_max_tokens = 4096
llm_temperature = 0.0
```

Load the configuration file:

```bash
poetry run swe-agent --config swe-agent.toml --issue 123 --repo .
```

---

## Usage

### Command-Line Interface

#### Basic Commands

```bash
# Fix an issue from GitHub URL
poetry run swe-agent --issue <issue_url> --repo <repo_path>

# Fix an issue by number (current repository)
poetry run swe-agent --issue <issue_number> --repo .

# Resume a previous session
poetry run swe-agent --resume <session_id>

# Get the status of a running session
poetry run swe-agent --status <session_id>
```

#### Advanced Options

```bash
# Verbose output
poetry run swe-agent --issue 123 --repo . --verbose

# Quiet mode (minimal output)
poetry run swe-agent --issue 123 --repo . --quiet

# Custom configuration file
poetry run swe-agent --issue 123 --repo . --config custom-config.toml

# Skip specific stages (for debugging)
poetry run swe-agent --issue 123 --repo . --skip-validation

# Generate multiple patch candidates
poetry run swe-agent --issue 123 --repo . --beam-search 5
```

### Programmatic Usage

You can also use SWE Agent as a Python library:

```python
from swe_agent.orchestrator.pipeline import PipelineOrchestrator
from swe_agent.config import load_config
from swe_agent.types import IssueContext, RepositoryContext

# Load configuration
config = load_config()

# Create issue context
issue = IssueContext(
    issue_id="123",
    title="Bug in login function",
    body="The login function throws an error...",
    parsed={"error_messages": ["ValueError: invalid input"]},
    metadata={"labels": ["bug"], "assignees": []}
)

# Create repository context
repo = RepositoryContext(
    path="/path/to/repo",
    git={"branch": "main", "commit": "abc123"},
    project_type="python",
    test_framework="pytest",
    dependencies={"python": "3.11"}
)

# Run the pipeline
orchestrator = PipelineOrchestrator(config=config)
result = orchestrator.run(issue=issue, repository=repo)

# Check result
if result.status == "success":
    print(f"Patch generated: {result.final_patch}")
else:
    print(f"Failed: {result.error.message}")
```

### Session Management

#### List Sessions

```bash
# List all sessions
ls -la .swe-agent/sessions/

# View session details
cat .swe-agent/sessions/<session_id>/state.json
```

#### Clean Up Old Sessions

```bash
# SWE Agent automatically keeps the 100 most recent sessions
# Manual cleanup (if needed)
rm -rf .swe-agent/sessions/<old_session_id>
```

#### Export Session Logs

```bash
# Copy session logs for debugging
cp -r .swe-agent/sessions/<session_id> ~/bug-fix-logs/
```

---

## Troubleshooting

### Common Errors and Solutions

#### Error: "Docker daemon not running"

**Symptom:**
```
Error: Cannot connect to Docker daemon
```

**Solution:**
```bash
# Start Docker daemon
sudo systemctl start docker  # Linux
# Or start Docker Desktop on macOS/Windows

# Verify Docker is running
docker ps
```

#### Error: "ANTHROPIC_API_KEY not set"

**Symptom:**
```
Error: Environment variable ANTHROPIC_API_KEY is not set
```

**Solution:**
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
# Or add to ~/.bashrc for persistence
```

#### Error: "Timeout exceeded"

**Symptom:**
```
Error: Stage timeout exceeded (300 seconds)
```

**Solution:**
```bash
# Increase timeout for specific stage
export SWE_AGENT_LOCALIZATION_TIMEOUT=600

# Or increase global timeout
export SWE_AGENT_GLOBAL_TIMEOUT=3600
```

#### Error: "Permission denied" (Docker)

**Symptom:**
```
Error: Permission denied while trying to connect to Docker
```

**Solution:**
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Logout and login again, then verify
docker ps
```

#### Error: "Repository not found"

**Symptom:**
```
Error: Repository path does not exist or is not a git repository
```

**Solution:**
```bash
# Verify path is correct
ls -la /path/to/repo

# Ensure it's a git repository
cd /path/to/repo && git status

# Use absolute paths
poetry run swe-agent --issue 123 --repo /absolute/path/to/repo
```

#### Error: "Test framework not detected"

**Symptom:**
```
Warning: Could not detect test framework
```

**Solution:**
```bash
# Ensure test files exist
ls tests/

# Common test frameworks and their indicators:
# - pytest: pytest.ini, pyproject.toml with [tool.pytest], or test_*.py files
# - jest: package.json with "jest" in scripts or devDependencies
# - junit: pom.xml with junit dependency or build.gradle

# Manually specify test command
export SWE_AGENT_TEST_COMMAND="pytest tests/"
```

#### Error: "Out of memory"

**Symptom:**
```
Error: Container killed due to memory limit
```

**Solution:**
```bash
# Increase Docker memory limit
export SWE_AGENT_DOCKER_MEMORY_LIMIT="8g"

# Or reduce concurrent sessions
# Kill other Docker containers
docker ps
docker stop <container_id>
```

### Debugging Tips

#### Enable Debug Logging

```bash
# Enable verbose debug output
export SWE_AGENT_LOG_LEVEL="DEBUG"
poetry run swe-agent --issue 123 --repo . --verbose
```

#### Inspect Session State

```bash
# View session state
cat .swe-agent/sessions/<session_id>/state.json | jq

# View execution logs
cat .swe-agent/sessions/<session_id>/execution.log

# View generated patches
ls .swe-agent/sessions/<session_id>/patches/
```

#### Manual Testing in Sandbox

```bash
# Access the Docker container manually
docker ps  # Find container ID
docker exec -it <container_id> /bin/bash

# Run commands inside the container
cd /workspace
pytest tests/
```

#### Check Resource Usage

```bash
# Monitor Docker resource usage
docker stats

# Check disk usage
du -sh .swe-agent/

# Check session sizes
du -sh .swe-agent/sessions/*
```

---

## FAQ

### General Questions

**Q: What types of bugs can SWE Agent fix?**

A: SWE Agent works best with:
- Logic errors with clear stack traces
- Test failures with reproducible steps
- Bugs in Python, JavaScript, Java, or Rust codebases
- Issues with clear error messages

It may struggle with:
- UI/UX issues without automated tests
- Performance optimization problems
- Design flaws requiring architectural changes
- Issues requiring external service dependencies

**Q: How long does it take to fix a bug?**

A: Typical execution times:
- Simple bugs: 5-10 minutes
- Medium complexity: 10-20 minutes
- Complex bugs: 20-30 minutes
- Maximum timeout: 30 minutes (configurable)

**Q: Can I use SWE Agent on private repositories?**

A: Yes! SWE Agent runs entirely locally. Your code never leaves your machine except for API calls to Anthropic's Claude (which only receive code snippets needed for analysis, not your entire codebase).

**Q: Does SWE Agent modify my repository?**

A: No. SWE Agent generates patches but does not apply them automatically. You must review and apply patches manually using `git apply`.

**Q: Can I run multiple SWE Agent sessions simultaneously?**

A: Yes, SWE Agent supports concurrent sessions. Each session runs in an isolated Docker container with its own session ID.

### Configuration Questions

**Q: How do I use a different Claude model?**

A:
```bash
export SWE_AGENT_LLM_MODEL="claude-opus-4-20250514"
```

**Q: How do I reduce API costs?**

A:
```bash
# Use smaller model
export SWE_AGENT_LLM_MODEL="claude-haiku-4-20250514"

# Reduce max tokens
export SWE_AGENT_LLM_MAX_TOKENS=2048

# Reduce retries
export SWE_AGENT_MAX_RETRIES=1
```

**Q: Can I disable the sandbox?**

A: No. The sandbox is required for safe code execution and cannot be disabled.

### Troubleshooting Questions

**Q: Why did localization fail to find the bug?**

A: Common reasons:
- Issue description is too vague (add more details, stack traces, or error messages)
- Bug is in a file not covered by search (check if file exists in repository)
- Repository is too large (try narrowing search with better issue description)

**Q: Why did reproduction fail?**

A: Common reasons:
- Missing dependencies (ensure requirements.txt or package.json is complete)
- Tests require external services (not supported in sandbox)
- Test setup is complex (add reproduction steps to issue description)

**Q: Why was my patch rejected?**

A: Common reasons:
- Patch introduces test regressions
- Patch has syntax errors
- Patch is too large (>50 lines)
- Patch doesn't fix the target test

**Q: How do I report a bug in SWE Agent?**

A: Open an issue on GitHub with:
- Session ID
- Issue URL or description
- Session logs (`.swe-agent/sessions/<session_id>/execution.log`)
- Error message

---

## Next Steps

- Read [EXAMPLES.md](./EXAMPLES.md) for detailed usage examples
- See [SYSTEM_DESIGN.md](../SYSTEM_DESIGN.md) for architecture details
- Explore [DEVELOPER.md](./DEVELOPER.md) for contributing guidelines (coming soon)

---

**Need Help?**

- GitHub Issues: https://github.com/yourusername/swe-agent/issues
- Documentation: https://github.com/yourusername/swe-agent/docs
- Email: support@swe-agent.dev
