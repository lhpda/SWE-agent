# SWE Agent

Windows 用户请先阅读 [Windows 运行说明](WINDOWS_RUN.md)，使用 `run.ps1` 加载本地模型配置。

An automated software engineering agent for bug fixing.

## Overview

SWE Agent is a multi-stage pipeline system that automatically:
- Localizes bugs from GitHub issues
- Reproduces errors in isolated environments
- Generates minimal patches
- Validates fixes without breaking existing tests

## Requirements

- Python 3.11+
- Docker (for sandboxed execution)
- Poetry (for dependency management)

## Installation

```bash
# Install dependencies
poetry install

# Verify installation
poetry run python --version
```

## Development

```bash
# Run tests
poetry run pytest

# Format code
poetry run black src/ tests/

# Lint code
poetry run ruff check src/ tests/

# Type check
poetry run mypy src/
```

## Project Structure

```
.
├── src/
│   └── swe_agent/       # Main package
├── tests/               # Test suite
├── docs/                # Documentation
├── pyproject.toml       # Project configuration
└── README.md
```

## License

MIT
