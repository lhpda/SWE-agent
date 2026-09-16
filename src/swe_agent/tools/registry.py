"""Tool registry for dynamic tool discovery and management.

This module provides a registry for registering and discovering tools.
Based on SYSTEM_DESIGN.md Section 3.6: Tool Layer.
"""

from typing import Dict, List, Optional

from swe_agent.logging import get_logger
from swe_agent.tools.base import Tool

logger = get_logger(__name__)


class ToolRegistry:
    """Registry for managing available tools.

    Provides:
    - Dynamic tool registration
    - Tool discovery by name
    - Schema generation for LLM integration
    """

    def __init__(self) -> None:
        """Initialize empty tool registry."""
        self._tools: Dict[str, Tool] = {}
        logger.info("tool_registry_initialized")

    def register(self, tool: Tool) -> None:
        """Register a tool in the registry.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If tool with same name is already registered
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")

        self._tools[tool.name] = tool
        logger.info("tool_registered", tool=tool.name)

    def unregister(self, tool_name: str) -> None:
        """Unregister a tool from the registry.

        Args:
            tool_name: Name of tool to unregister
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            logger.info("tool_unregistered", tool=tool_name)

    def has_tool(self, tool_name: str) -> bool:
        """Check if a tool is registered.

        Args:
            tool_name: Name of tool to check

        Returns:
            True if tool is registered
        """
        return tool_name in self._tools

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Get a registered tool by name.

        Args:
            tool_name: Name of tool to retrieve

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(tool_name)

    def list_tools(self) -> List[str]:
        """List all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_tool_schema(self, tool_name: str) -> Optional[Dict]:
        """Get JSON schema for a specific tool.

        This format is suitable for LLM tool calling APIs.

        Args:
            tool_name: Name of tool

        Returns:
            Tool schema dict or None if not found
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return None

        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_schema,
        }

    def get_all_schemas(self) -> List[Dict]:
        """Get JSON schemas for all registered tools.

        Returns:
            List of tool schema dicts
        """
        schemas = []
        for tool_name in self.list_tools():
            schema = self.get_tool_schema(tool_name)
            if schema:
                schemas.append(schema)
        return schemas


# Global registry instance
_global_registry: Optional[ToolRegistry] = None


def get_global_registry() -> ToolRegistry:
    """Get the global tool registry instance.

    Returns:
        Global ToolRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry
