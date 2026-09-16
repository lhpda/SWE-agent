"""Unit tests for Issue Parser (Task 3.1).

Tests verify parsing of various Issue formats including:
- Issues with stack traces (Python, JavaScript, Java)
- Vague/unclear Issues
- Multiple error messages
- Reproduction steps extraction
- Expected/actual behavior extraction
"""

import pytest

from src.swe_agent.agents.localization.parser import IssueParser
from src.swe_agent.types import IssueContext


class TestIssueParserBasic:
    """Basic parsing functionality tests."""

    def test_parse_simple_issue_with_python_stack_trace(self):
        """Test parsing Issue with Python stack trace."""
        issue_markdown = """
# Bug Report

The function fails when processing empty lists.

```python
Traceback (most recent call last):
  File "src/utils.py", line 42, in process_data
    result = data[0]
IndexError: list index out of range
```
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert isinstance(result, IssueContext)
        assert "error_messages" in result.parsed
        assert "stack_traces" in result.parsed
        assert len(result.parsed["stack_traces"]) == 1
        assert "IndexError" in result.parsed["error_messages"][0]
        assert "src/utils.py" in str(result.parsed["stack_traces"][0])
        assert result.parsed["stack_traces"][0]["language"] == "python"

    def test_parse_javascript_stack_trace(self):
        """Test parsing Issue with JavaScript stack trace."""
        issue_markdown = """
Getting an error when calling the API:

```
Error: Cannot read property 'id' of undefined
    at getUserData (src/api.js:25:15)
    at processRequest (src/handlers.js:102:8)
```
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert len(result.parsed["stack_traces"]) == 1
        assert result.parsed["stack_traces"][0]["language"] == "javascript"
        assert "src/api.js" in str(result.parsed["stack_traces"][0])
        assert "Cannot read property" in result.parsed["error_messages"][0]

    def test_parse_java_stack_trace(self):
        """Test parsing Issue with Java stack trace."""
        issue_markdown = """
Application crashes with:

```
java.lang.NullPointerException: Cannot invoke method on null object
    at com.example.Service.process(Service.java:156)
    at com.example.Controller.handle(Controller.java:89)
```
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert len(result.parsed["stack_traces"]) == 1
        assert result.parsed["stack_traces"][0]["language"] == "java"
        assert "Service.java" in str(result.parsed["stack_traces"][0])
        assert "NullPointerException" in result.parsed["error_messages"][0]


class TestIssueParserMultipleErrors:
    """Tests for extracting multiple error messages."""

    def test_extract_multiple_error_messages(self):
        """Test extracting multiple error messages from Issue."""
        issue_markdown = """
Two errors occur:

1. First error:
```
TypeError: Expected string, got int
```

2. Second error:
```
ValueError: Invalid format for date
```
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert len(result.parsed["error_messages"]) >= 2
        assert any("TypeError" in msg for msg in result.parsed["error_messages"])
        assert any("ValueError" in msg for msg in result.parsed["error_messages"])

    def test_extract_errors_from_different_formats(self):
        """Test extracting errors in various formats."""
        issue_markdown = """
Error: Connection failed
Exception: Database timeout
AssertionError: Expected 5, got 3
RuntimeError: Operation not permitted
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert len(result.parsed["error_messages"]) >= 4

    def test_extract_inline_errors(self):
        """Test extracting inline error messages."""
        issue_markdown = """
When I run the code, I get `AttributeError: 'NoneType' object has no attribute 'name'`
and then also `KeyError: 'user_id'` appears.
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert len(result.parsed["error_messages"]) >= 2
        assert any("AttributeError" in msg for msg in result.parsed["error_messages"])
        assert any("KeyError" in msg for msg in result.parsed["error_messages"])


class TestIssueParserReproductionSteps:
    """Tests for extracting reproduction steps."""

    def test_extract_numbered_reproduction_steps(self):
        """Test extracting numbered reproduction steps."""
        issue_markdown = """
## Steps to Reproduce

1. Install the package
2. Run `python main.py`
3. Click the submit button
4. Error appears
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert "reproduction_steps" in result.parsed
        assert len(result.parsed["reproduction_steps"]) >= 3
        assert any("Install" in step for step in result.parsed["reproduction_steps"])

    def test_extract_code_block_reproduction(self):
        """Test extracting code blocks as reproduction steps."""
        issue_markdown = """
To reproduce:

```python
import mylib
obj = mylib.create()
obj.process()  # Fails here
```
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert "reproduction_steps" in result.parsed
        assert len(result.parsed["reproduction_steps"]) > 0
        assert any("import" in step.lower() or "python" in step.lower()
                  for step in result.parsed["reproduction_steps"])

    def test_extract_mixed_reproduction_steps(self):
        """Test extracting reproduction steps with mixed formats."""
        issue_markdown = """
How to reproduce:

1. Clone the repo
2. Run: `npm install`
3. Execute the following:
   ```js
   const app = require('./app');
   app.start();
   ```
4. Navigate to http://localhost:3000
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert len(result.parsed["reproduction_steps"]) >= 3


class TestIssueParserExpectedActual:
    """Tests for extracting expected and actual behavior."""

    def test_extract_expected_and_actual_behavior(self):
        """Test extracting expected and actual behavior."""
        issue_markdown = """
**Expected behavior:**
The function should return an empty list when no matches are found.

**Actual behavior:**
The function raises an exception instead.
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert "expected_behavior" in result.parsed
        assert "actual_behavior" in result.parsed
        assert result.parsed["expected_behavior"] is not None
        assert result.parsed["actual_behavior"] is not None
        assert "empty list" in result.parsed["expected_behavior"].lower()
        assert "exception" in result.parsed["actual_behavior"].lower()

    def test_extract_should_be_but_got_pattern(self):
        """Test extracting 'should be' and 'but got' patterns."""
        issue_markdown = """
The result should be 42, but got 0 instead.
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        # Should extract some form of expected/actual
        assert ("expected_behavior" in result.parsed or
                "actual_behavior" in result.parsed)

    def test_extract_expected_vs_actual_table(self):
        """Test extracting expected vs actual from comparison."""
        issue_markdown = """
| Expected | Actual |
|----------|--------|
| Success  | Error  |
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        # Should attempt to extract comparison
        parsed = result.parsed
        assert isinstance(parsed, dict)


class TestIssueParserVagueIssues:
    """Tests for parsing vague or unclear Issues."""

    def test_parse_vague_issue_without_stack_trace(self):
        """Test parsing vague Issue without technical details."""
        issue_markdown = """
The app doesn't work properly. Sometimes it crashes.
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert isinstance(result, IssueContext)
        assert result.parsed["stack_traces"] == []
        assert len(result.parsed["error_messages"]) == 0
        assert "vague" in result.parsed.get("quality", "").lower() or \
               result.parsed.get("confidence", 1.0) < 0.5

    def test_parse_minimal_issue(self):
        """Test parsing minimal Issue with little information."""
        issue_markdown = "Bug in code"
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert isinstance(result, IssueContext)
        assert result.body == issue_markdown

    def test_parse_descriptive_but_no_error_issue(self):
        """Test parsing descriptive Issue without error details."""
        issue_markdown = """
When users try to upload large files, the process takes too long
and they give up. This impacts user experience significantly.
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert len(result.parsed["error_messages"]) == 0
        assert len(result.parsed["stack_traces"]) == 0


class TestIssueParserErrorHandling:
    """Tests for error handling and edge cases."""

    def test_parse_empty_string(self):
        """Test parsing empty string returns clear error."""
        parser = IssueParser()
        with pytest.raises(ValueError, match="empty|blank"):
            parser.parse("")

    def test_parse_none_input(self):
        """Test parsing None returns clear error."""
        parser = IssueParser()
        with pytest.raises((ValueError, TypeError)):
            parser.parse(None)

    def test_parse_extremely_long_issue(self):
        """Test parsing very long Issue doesn't crash."""
        issue_markdown = "Line of text\n" * 10000
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert isinstance(result, IssueContext)

    def test_parse_issue_with_special_characters(self):
        """Test parsing Issue with special characters."""
        issue_markdown = """
Error: Invalid input «test» — причина неизвестна
```
File "测试.py", line 1
SyntaxError: invalid syntax
```
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert isinstance(result, IssueContext)


class TestIssueParserExtractMethods:
    """Tests for individual extraction methods."""

    def test_extract_error_messages_method(self):
        """Test extract_error_messages method directly."""
        issue_markdown = """
Error: Something went wrong
TypeError: Bad type
"""
        parser = IssueParser()
        parser.parse(issue_markdown)
        errors = parser.extract_error_messages()

        assert isinstance(errors, list)
        assert len(errors) >= 2

    def test_extract_stack_traces_method(self):
        """Test extract_stack_traces method directly."""
        issue_markdown = """
```
Traceback (most recent call last):
  File "test.py", line 1, in <module>
ValueError: test
```
"""
        parser = IssueParser()
        parser.parse(issue_markdown)
        traces = parser.extract_stack_traces()

        assert isinstance(traces, list)
        assert len(traces) >= 1

    def test_extract_reproduction_steps_method(self):
        """Test extract_reproduction_steps method directly."""
        issue_markdown = """
Steps:
1. Do this
2. Do that
"""
        parser = IssueParser()
        parser.parse(issue_markdown)
        steps = parser.extract_reproduction_steps()

        assert isinstance(steps, list)

    def test_extract_expected_actual_method(self):
        """Test extract_expected_actual method directly."""
        issue_markdown = """
Expected: success
Actual: failure
"""
        parser = IssueParser()
        parser.parse(issue_markdown)
        expected, actual = parser.extract_expected_actual()

        assert expected is not None or actual is not None


class TestIssueParserIntegration:
    """Integration tests with complete realistic Issues."""

    def test_parse_complete_bug_report(self):
        """Test parsing complete, well-formatted bug report."""
        issue_markdown = """
# Database Connection Fails on Startup

## Description
The application fails to connect to the database when starting up.

## Steps to Reproduce
1. Start the application with `python app.py`
2. Check the logs
3. See error message

## Expected Behavior
Application should connect to database successfully.

## Actual Behavior
Application crashes with connection error.

## Error Output
```
Traceback (most recent call last):
  File "app.py", line 15, in main
    db.connect()
  File "db.py", line 28, in connect
    raise ConnectionError("Failed to connect")
ConnectionError: Failed to connect to database
```

## Environment
- Python 3.9
- PostgreSQL 14
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert len(result.parsed["error_messages"]) >= 1
        assert len(result.parsed["stack_traces"]) >= 1
        assert len(result.parsed["reproduction_steps"]) >= 1
        assert result.parsed["expected_behavior"] is not None
        assert result.parsed["actual_behavior"] is not None

    def test_parse_github_style_issue(self):
        """Test parsing typical GitHub Issue format."""
        issue_markdown = """
### Bug Description
When calling `process_data(None)`, the function crashes.

### To Reproduce
```python
from mylib import process_data
process_data(None)  # Raises exception
```

### Expected behavior
Should handle None gracefully and return empty result.

### Actual behavior
Crashes with AttributeError.

### Screenshots/Logs
```
AttributeError: 'NoneType' object has no attribute 'items'
```
"""
        parser = IssueParser()
        result = parser.parse(issue_markdown)

        assert isinstance(result, IssueContext)
        assert len(result.parsed["error_messages"]) >= 1
