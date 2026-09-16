"""Tests for tool base interface and registry (Task 1.1)."""

import pytest

from swe_agent.tools.base import Tool, ToolResult
from swe_agent.tools.registry import ToolRegistry


class TestToolInterface:
    """Test the Tool abstract base class."""

    def test_tool_has_required_attributes(self):
        """Test that Tool defines required attributes."""
        # Create a concrete implementation
        class DummyTool(Tool):
            name = "dummy"
            description = "A dummy tool"
            parameters_schema = {"type": "object", "properties": {}}

            def execute(self, **kwargs):
                return ToolResult(output="dummy output", truncated=False)

        tool = DummyTool()
        assert tool.name == "dummy"
        assert tool.description == "A dummy tool"
        assert tool.parameters_schema is not None

    def test_tool_execute_returns_tool_result(self):
        """Test that execute returns ToolResult."""
        class TestTool(Tool):
            name = "test"
            description = "Test tool"
            parameters_schema = {"type": "object", "properties": {}}

            def execute(self, **kwargs):
                return ToolResult(output="test", truncated=False)

        tool = TestTool()
        result = tool.execute()

        assert isinstance(result, ToolResult)
        assert result.output == "test"
        assert result.truncated is False

    def test_tool_cannot_be_instantiated_without_implementation(self):
        """Test that Tool cannot be instantiated directly."""
        # Tool is abstract, should not be instantiable without implementing abstract methods
        with pytest.raises(TypeError):
            Tool()  # type: ignore


class TestToolResult:
    """Test ToolResult class."""

    def test_tool_result_creation(self):
        """Test creating ToolResult."""
        result = ToolResult(output="test output", truncated=False)

        assert result.output == "test output"
        assert result.truncated is False

    def test_tool_result_with_error(self):
        """Test ToolResult with error."""
        result = ToolResult(output=None, truncated=False, error="Something went wrong")

        assert result.output is None
        assert result.error == "Something went wrong"

    def test_tool_result_with_metadata(self):
        """Test ToolResult with metadata."""
        result = ToolResult(
            output="data",
            truncated=True,
            metadata={"execution_time": 1.5, "cached": False},
        )

        assert result.metadata["execution_time"] == 1.5
        assert result.metadata["cached"] is False


class TestParameterValidation:
    """Test parameter validation."""

    def test_validate_parameters_with_valid_input(self):
        """Test parameter validation with valid input."""
        class ValidatedTool(Tool):
            name = "validated"
            description = "Validated tool"
            parameters_schema = {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            }

            def execute(self, **kwargs):
                return ToolResult(output=kwargs.get("query"), truncated=False)

        tool = ValidatedTool()
        result = tool.validate_parameters({"query": "test", "limit": 10})

        assert result is True

    def test_validate_parameters_with_missing_required(self):
        """Test parameter validation with missing required field."""
        class StrictTool(Tool):
            name = "strict"
            description = "Strict tool"
            parameters_schema = {
                "type": "object",
                "properties": {"required_field": {"type": "string"}},
                "required": ["required_field"],
            }

            def execute(self, **kwargs):
                return ToolResult(output="ok", truncated=False)

        tool = StrictTool()
        result = tool.validate_parameters({})

        assert result is False

    def test_validate_parameters_with_wrong_type(self):
        """Test parameter validation with wrong type."""
        class TypedTool(Tool):
            name = "typed"
            description = "Typed tool"
            parameters_schema = {
                "type": "object",
                "properties": {"count": {"type": "integer"}},
            }

            def execute(self, **kwargs):
                return ToolResult(output="ok", truncated=False)

        tool = TypedTool()
        result = tool.validate_parameters({"count": "not a number"})

        assert result is False


class TestOutputTruncation:
    """Test output truncation mechanism."""

    def test_truncate_output_under_limit(self):
        """Test that output under limit is not truncated."""
        class TruncatingTool(Tool):
            name = "truncating"
            description = "Truncating tool"
            parameters_schema = {"type": "object", "properties": {}}
            max_output_size = 100

            def execute(self, **kwargs):
                output = "short output"
                return self.truncate_output(output)

        tool = TruncatingTool()
        result = tool.execute()

        assert result.output == "short output"
        assert result.truncated is False

    def test_truncate_output_over_limit(self):
        """Test that output over limit is truncated."""
        class TruncatingTool(Tool):
            name = "truncating"
            description = "Truncating tool"
            parameters_schema = {"type": "object", "properties": {}}
            max_output_size = 50  # 50 bytes

            def execute(self, **kwargs):
                output = "x" * 100  # 100 bytes
                return self.truncate_output(output)

        tool = TruncatingTool()
        result = tool.execute()

        # Output should be truncated and have marker
        assert result.truncated is True
        assert "[truncated" in result.output
        # The actual output is 50 bytes + marker, so longer than 50 but shows truncation happened
        assert result.output.startswith("x" * 50)

    def test_default_max_output_size(self):
        """Test default max output size is 10KB."""
        class DefaultTool(Tool):
            name = "default"
            description = "Default tool"
            parameters_schema = {"type": "object", "properties": {}}

            def execute(self, **kwargs):
                return ToolResult(output="ok", truncated=False)

        tool = DefaultTool()
        assert tool.max_output_size == 10 * 1024  # 10KB


class TestToolRegistry:
    """Test ToolRegistry."""

    def test_create_registry(self):
        """Test creating a ToolRegistry."""
        registry = ToolRegistry()
        assert registry is not None

    def test_register_tool(self):
        """Test registering a tool."""
        registry = ToolRegistry()

        class MyTool(Tool):
            name = "my_tool"
            description = "My tool"
            parameters_schema = {"type": "object", "properties": {}}

            def execute(self, **kwargs):
                return ToolResult(output="ok", truncated=False)

        tool = MyTool()
        registry.register(tool)

        assert registry.has_tool("my_tool")

    def test_get_registered_tool(self):
        """Test getting a registered tool."""
        registry = ToolRegistry()

        class FetchTool(Tool):
            name = "fetch"
            description = "Fetch tool"
            parameters_schema = {"type": "object", "properties": {}}

            def execute(self, **kwargs):
                return ToolResult(output="fetched", truncated=False)

        tool = FetchTool()
        registry.register(tool)

        retrieved = registry.get_tool("fetch")
        assert retrieved is not None
        assert retrieved.name == "fetch"

    def test_get_nonexistent_tool_returns_none(self):
        """Test getting a tool that doesn't exist."""
        registry = ToolRegistry()

        result = registry.get_tool("nonexistent")
        assert result is None

    def test_list_all_tools(self):
        """Test listing all registered tools."""
        registry = ToolRegistry()

        class Tool1(Tool):
            name = "tool1"
            description = "Tool 1"
            parameters_schema = {"type": "object", "properties": {}}

            def execute(self, **kwargs):
                return ToolResult(output="1", truncated=False)

        class Tool2(Tool):
            name = "tool2"
            description = "Tool 2"
            parameters_schema = {"type": "object", "properties": {}}

            def execute(self, **kwargs):
                return ToolResult(output="2", truncated=False)

        registry.register(Tool1())
        registry.register(Tool2())

        tools = registry.list_tools()
        assert len(tools) == 2
        assert "tool1" in tools
        assert "tool2" in tools

    def test_register_duplicate_tool_raises_error(self):
        """Test that registering duplicate tool raises error."""
        registry = ToolRegistry()

        class DupeTool(Tool):
            name = "dupe"
            description = "Duplicate"
            parameters_schema = {"type": "object", "properties": {}}

            def execute(self, **kwargs):
                return ToolResult(output="ok", truncated=False)

        registry.register(DupeTool())

        with pytest.raises(ValueError, match="already registered"):
            registry.register(DupeTool())

    def test_unregister_tool(self):
        """Test unregistering a tool."""
        registry = ToolRegistry()

        class RemovableTool(Tool):
            name = "removable"
            description = "Removable"
            parameters_schema = {"type": "object", "properties": {}}

            def execute(self, **kwargs):
                return ToolResult(output="ok", truncated=False)

        registry.register(RemovableTool())
        assert registry.has_tool("removable")

        registry.unregister("removable")
        assert not registry.has_tool("removable")

    def test_get_tool_schema(self):
        """Test getting tool schema for LLM."""
        registry = ToolRegistry()

        class SchemaTool(Tool):
            name = "schema_tool"
            description = "A tool with schema"
            parameters_schema = {
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "First param"},
                    "param2": {"type": "integer", "description": "Second param"},
                },
                "required": ["param1"],
            }

            def execute(self, **kwargs):
                return ToolResult(output="ok", truncated=False)

        registry.register(SchemaTool())

        schema = registry.get_tool_schema("schema_tool")
        assert schema is not None
        assert schema["name"] == "schema_tool"
        assert schema["description"] == "A tool with schema"
        assert "parameters" in schema
        assert schema["parameters"]["required"] == ["param1"]

    def test_get_all_tools_schemas(self):
        """Test getting all tools schemas for LLM."""
        registry = ToolRegistry()

        class ToolA(Tool):
            name = "tool_a"
            description = "Tool A"
            parameters_schema = {"type": "object", "properties": {}}

            def execute(self, **kwargs):
                return ToolResult(output="a", truncated=False)

        class ToolB(Tool):
            name = "tool_b"
            description = "Tool B"
            parameters_schema = {"type": "object", "properties": {}}

            def execute(self, **kwargs):
                return ToolResult(output="b", truncated=False)

        registry.register(ToolA())
        registry.register(ToolB())

        schemas = registry.get_all_schemas()
        assert len(schemas) == 2
        assert any(s["name"] == "tool_a" for s in schemas)
        assert any(s["name"] == "tool_b" for s in schemas)
