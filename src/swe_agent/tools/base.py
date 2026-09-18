"""Base interface for tools in SWE Agent.

This module defines the abstract Tool class and related types.
Based on SYSTEM_DESIGN.md Section 3.6: Tool Layer.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import jsonschema
from pydantic import BaseModel, Field

from swe_agent.logging import get_logger

logger = get_logger(__name__)


class ToolResult(BaseModel):
    """Result from a tool execution.

    Attributes:
        output: Tool output (string or structured data)
        truncated: Whether output was truncated
        error: Error message if execution failed
        metadata: Additional metadata about execution
    """

    output: Optional[Any] = Field(None, description="Tool output")
    truncated: bool = Field(..., description="Whether output was truncated")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution metadata")

    model_config = {"extra": "forbid"}


class Tool(ABC):
    """Abstract base class for all tools.

    All tools must implement:
    - name: Unique tool identifier
    - description: Human-readable description
    - parameters_schema: JSON Schema for parameters
    - execute(): Main execution logic

    Tools automatically support:
    - Parameter validation (JSON Schema)
    - Output truncation (10KB default limit)
    - Logging and error handling
    """

    name: str
    description: str
    parameters_schema: Dict[str, Any]
    max_output_size: int = 10 * 1024  # 10KB default (from SYSTEM_DESIGN.md Section 5.1)

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with given parameters.

        Args:
            **kwargs: Tool parameters (validated against parameters_schema)

        Returns:
            ToolResult with output or error
        """
        pass

    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """Validate parameters against JSON Schema.

        Args:
            params: Parameters to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            jsonschema.validate(instance=params, schema=self.parameters_schema)
            return True
        except jsonschema.ValidationError as e:
            logger.warning(
                "parameter_validation_failed",
                tool=self.name,
                error=str(e),
            )
            return False
        except jsonschema.SchemaError as e:
            logger.error(
                "invalid_parameter_schema",
                tool=self.name,
                error=str(e),
            )
            return False

    def truncate_output(self, output: str) -> ToolResult:
        """Truncate output if it exceeds max_output_size.

        Args:
            output: Output string to potentially truncate

        Returns:
            ToolResult with truncated flag set appropriately
        """
        if not isinstance(output, str):
            # Non-string output, return as-is
            return ToolResult(output=output, truncated=False)

        output_bytes = len(output.encode("utf-8"))

        if output_bytes <= self.max_output_size:
            return ToolResult(output=output, truncated=False)

        # Truncate to max_output_size
        truncated_output = output[: self.max_output_size]

        # Add truncation marker
        marker = f"\n\n[truncated: original size {output_bytes} bytes, showing first {self.max_output_size} bytes]"
        truncated_output += marker

        logger.debug(
            "output_truncated",
            tool=self.name,
            original_size=output_bytes,
            truncated_size=len(truncated_output),
        )

        return ToolResult(output=truncated_output, truncated=True)

    def __repr__(self) -> str:
        """String representation of tool."""
        return f"<Tool: {self.name}>"
