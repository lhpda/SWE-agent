"""Configuration management for SWE Agent.

This module defines global configuration with support for:
- Default values from SYSTEM_DESIGN.md specifications
- Environment variable overrides
- File-based configuration (optional)
"""

import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    """Global configuration for SWE Agent.

    All timeout values are in seconds.
    All size limits are in bytes unless otherwise specified.
    """

    # ========================================================================
    # Timeout Configuration (from Section 2.2)
    # ========================================================================

    localization_timeout: int = Field(
        default=300,  # 5 minutes
        gt=0,
        description="Timeout for localization stage in seconds",
    )

    reproduction_timeout: int = Field(
        default=480,  # 8 minutes
        gt=0,
        description="Timeout for reproduction stage in seconds",
    )

    patch_generation_timeout: int = Field(
        default=360,  # 6 minutes
        gt=0,
        description="Timeout for patch generation stage in seconds",
    )

    validation_timeout: int = Field(
        default=600,  # 10 minutes
        gt=0,
        description="Timeout for validation stage in seconds",
    )

    global_timeout: int = Field(
        default=1800,  # 30 minutes
        gt=0,
        description="Global pipeline timeout in seconds",
    )

    # ========================================================================
    # Retry Configuration (from Section 2.2)
    # ========================================================================

    max_retries: int = Field(
        default=3,
        ge=0,
        description="Global maximum retry count",
    )

    localization_max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retries for localization stage",
    )

    reproduction_max_retries: int = Field(
        default=5,
        ge=0,
        description="Maximum retries for reproduction stage",
    )

    patch_max_retries: int = Field(
        default=5,
        ge=0,
        description="Maximum retries for patch generation (beam search)",
    )

    validation_max_retries: int = Field(
        default=1,
        ge=0,
        description="Maximum retries for validation per patch",
    )

    # ========================================================================
    # Output Limits (from Section 5.1)
    # ========================================================================

    max_tool_output_size: int = Field(
        default=10 * 1024,  # 10KB
        gt=0,
        description="Maximum tool output size in bytes",
    )

    max_test_output_size: int = Field(
        default=5 * 1024,  # 5KB
        gt=0,
        description="Maximum test output size in bytes",
    )

    max_file_size: int = Field(
        default=50000,  # 50,000 characters
        gt=0,
        description="Maximum file content size in characters",
    )

    max_search_results: int = Field(
        default=100,
        gt=0,
        description="Maximum number of search results",
    )

    # ========================================================================
    # Docker Resource Limits (from Section 3.7)
    # ========================================================================

    docker_cpu_limit: int = Field(
        default=2,
        gt=0,
        description="Docker CPU limit in cores",
    )

    docker_memory_limit: str = Field(
        default="4g",
        description="Docker memory limit (e.g., '4g', '2048m')",
    )

    docker_timeout: int = Field(
        default=600,  # 10 minutes
        gt=0,
        description="Docker command execution timeout in seconds",
    )

    # ========================================================================
    # Storage Configuration (from Section 3.8)
    # ========================================================================

    storage_base_path: Path = Field(
        default=Path(".swe-agent"),
        description="Base path for storing session data",
    )

    max_session_size: int = Field(
        default=1024 * 1024 * 1024,  # 1GB
        gt=0,
        description="Maximum size per session in bytes",
    )

    max_sessions: int = Field(
        default=100,
        gt=0,
        description="Maximum number of sessions to retain (FIFO)",
    )

    # ========================================================================
    # Logging Configuration (from Section 8.3)
    # ========================================================================

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging level",
    )

    log_format: Literal["json", "console"] = Field(
        default="json",
        description="Log output format",
    )

    # ========================================================================
    # LLM Configuration
    # ========================================================================

    llm_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="LLM model to use",
    )

    llm_max_tokens: int = Field(
        default=4096,
        gt=0,
        description="Maximum tokens per LLM request",
    )

    llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="LLM temperature",
    )

    # ========================================================================
    # Computed Properties
    # ========================================================================

    @property
    def sessions_path(self) -> Path:
        """Get the sessions storage path."""
        return self.storage_base_path / "sessions"

    @property
    def cache_path(self) -> Path:
        """Get the cache storage path."""
        return self.storage_base_path / "cache"

    model_config = {"extra": "forbid"}

    @field_validator("localization_timeout", "reproduction_timeout",
                     "patch_generation_timeout", "validation_timeout",
                     "global_timeout", "docker_timeout")
    @classmethod
    def validate_positive_timeout(cls, v: int) -> int:
        """Validate that timeout values are positive."""
        if v <= 0:
            raise ValueError(f"Timeout must be positive, got {v}")
        return v

    @field_validator("max_retries", "localization_max_retries",
                     "reproduction_max_retries", "patch_max_retries",
                     "validation_max_retries")
    @classmethod
    def validate_non_negative_retries(cls, v: int) -> int:
        """Validate that retry values are non-negative."""
        if v < 0:
            raise ValueError(f"Retries must be non-negative, got {v}")
        return v

    @field_validator("max_tool_output_size", "max_test_output_size",
                     "max_file_size", "max_session_size")
    @classmethod
    def validate_positive_size(cls, v: int) -> int:
        """Validate that size limits are positive."""
        if v <= 0:
            raise ValueError(f"Size limit must be positive, got {v}")
        return v


def load_config(config_file: Optional[str] = None) -> Config:
    """Load configuration from environment variables and optional file.

    Environment variables take precedence over file configuration.
    Variable names follow the pattern: SWE_AGENT_<FIELD_NAME>

    Args:
        config_file: Optional path to TOML config file

    Returns:
        Loaded Config instance
    """
    config_dict = {}

    # Load from file if provided
    if config_file and Path(config_file).exists():
        try:
            import tomli
            with open(config_file, "rb") as f:
                file_config = tomli.load(f)
                config_dict.update(file_config.get("swe_agent", {}))
        except ImportError:
            # tomli not available, skip file loading
            pass
        except Exception:
            # File parsing failed, skip
            pass

    # Override with environment variables
    env_mappings = {
        "SWE_AGENT_LOCALIZATION_TIMEOUT": "localization_timeout",
        "SWE_AGENT_REPRODUCTION_TIMEOUT": "reproduction_timeout",
        "SWE_AGENT_PATCH_GENERATION_TIMEOUT": "patch_generation_timeout",
        "SWE_AGENT_VALIDATION_TIMEOUT": "validation_timeout",
        "SWE_AGENT_GLOBAL_TIMEOUT": "global_timeout",
        "SWE_AGENT_MAX_RETRIES": "max_retries",
        "SWE_AGENT_LOCALIZATION_MAX_RETRIES": "localization_max_retries",
        "SWE_AGENT_REPRODUCTION_MAX_RETRIES": "reproduction_max_retries",
        "SWE_AGENT_PATCH_MAX_RETRIES": "patch_max_retries",
        "SWE_AGENT_VALIDATION_MAX_RETRIES": "validation_max_retries",
        "SWE_AGENT_MAX_TOOL_OUTPUT_SIZE": "max_tool_output_size",
        "SWE_AGENT_MAX_TEST_OUTPUT_SIZE": "max_test_output_size",
        "SWE_AGENT_MAX_FILE_SIZE": "max_file_size",
        "SWE_AGENT_MAX_SEARCH_RESULTS": "max_search_results",
        "SWE_AGENT_DOCKER_CPU_LIMIT": "docker_cpu_limit",
        "SWE_AGENT_DOCKER_MEMORY_LIMIT": "docker_memory_limit",
        "SWE_AGENT_DOCKER_TIMEOUT": "docker_timeout",
        "SWE_AGENT_STORAGE_BASE_PATH": "storage_base_path",
        "SWE_AGENT_MAX_SESSION_SIZE": "max_session_size",
        "SWE_AGENT_MAX_SESSIONS": "max_sessions",
        "SWE_AGENT_LOG_LEVEL": "log_level",
        "SWE_AGENT_LOG_FORMAT": "log_format",
        "SWE_AGENT_LLM_MODEL": "llm_model",
        "SWE_AGENT_LLM_MAX_TOKENS": "llm_max_tokens",
        "SWE_AGENT_LLM_TEMPERATURE": "llm_temperature",
    }

    for env_var, field_name in env_mappings.items():
        value = os.environ.get(env_var)
        if value is not None:
            # Try to convert to appropriate type
            try:
                # Get field type from Config model
                field_info = Config.model_fields[field_name]
                field_type = field_info.annotation

                # Convert based on type
                if field_type == int or (hasattr(field_type, "__origin__") and int in getattr(field_type, "__args__", [])):
                    config_dict[field_name] = int(value)
                elif field_type == float:
                    config_dict[field_name] = float(value)
                elif field_type == Path:
                    config_dict[field_name] = Path(value)
                else:
                    config_dict[field_name] = value
            except (ValueError, KeyError):
                # If conversion fails, skip this variable
                pass

    return Config(**config_dict)
