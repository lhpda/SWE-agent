"""Tests for LogAnalyzer - error log parsing and analysis.

Task 4.2: Error Log Analyzer
Tests validate Python, JavaScript, and Java stack trace parsing,
error type identification, root cause extraction, and log truncation.
"""

import pytest
from swe_agent.agents.reproduction.log_analyzer import LogAnalyzer


class TestPythonStackTracesParsing:
    """Test Python stack trace parsing capabilities."""

    def test_parse_simple_python_exception(self):
        """Test parsing a simple Python exception with stack trace."""
        log_content = """
Running tests...
Traceback (most recent call last):
  File "src/calculator.py", line 15, in divide
    result = a / b
ZeroDivisionError: division by zero
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        stack_traces = analyzer.extract_stack_traces()

        assert len(stack_traces) == 1
        assert "Traceback (most recent call last)" in stack_traces[0]
        assert "ZeroDivisionError" in stack_traces[0]

    def test_parse_python_assertion_error(self):
        """Test parsing Python AssertionError from test failures."""
        log_content = """
============================= test session starts ==============================
test_math.py::test_addition FAILED

    def test_addition():
>       assert add(2, 2) == 5
E       AssertionError: assert 4 == 5

test_math.py:10: AssertionError
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        error_type = analyzer.identify_error_type()

        assert error_type == "AssertionError"

    def test_parse_multiple_python_stack_traces(self):
        """Test parsing multiple stack traces from log."""
        log_content = """
Traceback (most recent call last):
  File "test_a.py", line 5, in test_func
    raise ValueError("first error")
ValueError: first error

Traceback (most recent call last):
  File "test_b.py", line 10, in test_another
    raise TypeError("second error")
TypeError: second error
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        stack_traces = analyzer.extract_stack_traces()

        assert len(stack_traces) == 2
        assert "ValueError" in stack_traces[0]
        assert "TypeError" in stack_traces[1]

    def test_extract_python_file_and_line_number(self):
        """Test extracting file and line number from Python stack trace."""
        log_content = """
Traceback (most recent call last):
  File "/usr/lib/python3.11/pathlib.py", line 1234, in _init
    self._parts = parts
  File "src/mymodule/core.py", line 42, in process
    result = compute(data)
  File "src/mymodule/utils.py", line 87, in compute
    return data / 0
ZeroDivisionError: division by zero
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        root_cause = analyzer.extract_root_cause()

        # Should extract first project file (not stdlib)
        assert root_cause["file"] == "src/mymodule/core.py"
        assert root_cause["line"] == 42

    def test_python_nested_exception(self):
        """Test parsing nested Python exceptions with context."""
        log_content = """
Traceback (most recent call last):
  File "app.py", line 100, in main
    process_data()
  File "app.py", line 50, in process_data
    load_file("data.json")
  File "app.py", line 20, in load_file
    with open(filename) as f:
FileNotFoundError: [Errno 2] No such file or directory: 'data.json'
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        error_type = analyzer.identify_error_type()
        root_cause = analyzer.extract_root_cause()

        assert error_type == "FileNotFoundError"
        assert root_cause["file"] == "app.py"
        assert root_cause["line"] == 100


class TestJavaScriptStackTracesParsing:
    """Test JavaScript/Node.js stack trace parsing."""

    def test_parse_simple_javascript_error(self):
        """Test parsing a simple JavaScript error stack."""
        log_content = """
  Test suite failed to run

    Error: Cannot find module './missing-module'
        at Function.Module._resolveFilename (node:internal/modules/cjs/loader:933:15)
        at Function.Module._load (node:internal/modules/cjs/loader:778:27)
        at Module.require (src/app.js:15:20)
        at Object.<anonymous> (src/index.js:5:1)
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        stack_traces = analyzer.extract_stack_traces()

        assert len(stack_traces) == 1
        assert "Error: Cannot find module" in stack_traces[0]

    def test_extract_javascript_file_and_line(self):
        """Test extracting file and line from JavaScript stack trace."""
        log_content = """
Error: Expected true to be false
    at Object.<anonymous> (node_modules/jest/lib/runner.js:100:5)
    at processTicksAndRejections (node:internal/process/task_queues:96:5)
    at testFunction (src/calculator.test.js:25:15)
    at Object.testCase (src/calculator.test.js:10:3)
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        root_cause = analyzer.extract_root_cause()

        # Should skip node_modules and node: internal
        assert root_cause["file"] == "src/calculator.test.js"
        assert root_cause["line"] == 25

    def test_parse_jest_assertion_error(self):
        """Test parsing Jest assertion error."""
        log_content = """
 FAIL  src/math.test.js
  ● Math › addition

    expect(received).toBe(expected)

    Expected: 5
    Received: 4

      10 |   test('addition', () => {
      11 |     const result = add(2, 2);
    > 12 |     expect(result).toBe(5);
         |                    ^
      13 |   });

    at Object.<anonymous> (src/math.test.js:12:20)
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        root_cause = analyzer.extract_root_cause()

        assert root_cause["file"] == "src/math.test.js"
        assert root_cause["line"] == 12


class TestJavaStackTracesParsing:
    """Test Java stack trace parsing."""

    def test_parse_java_exception(self):
        """Test parsing Java exception stack trace."""
        log_content = """
Exception in thread "main" java.lang.NullPointerException: Cannot invoke method on null object
    at com.example.app.Calculator.divide(Calculator.java:45)
    at com.example.app.Main.main(Main.java:12)
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        stack_traces = analyzer.extract_stack_traces()
        error_type = analyzer.identify_error_type()

        assert len(stack_traces) == 1
        assert "NullPointerException" in stack_traces[0]
        assert error_type == "NullPointerException"

    def test_extract_java_file_and_line(self):
        """Test extracting file and line from Java stack trace."""
        log_content = """
java.lang.ArrayIndexOutOfBoundsException: Index 5 out of bounds for length 3
    at java.base/java.util.ArrayList.rangeCheck(ArrayList.java:659)
    at com.myapp.service.DataProcessor.process(DataProcessor.java:123)
    at com.myapp.Main.run(Main.java:56)
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        root_cause = analyzer.extract_root_cause()

        # Should skip java.base internal classes
        assert root_cause["file"] == "DataProcessor.java"
        assert root_cause["line"] == 123


class TestErrorTypeIdentification:
    """Test error type identification across languages."""

    def test_identify_python_exception_types(self):
        """Test identifying various Python exception types."""
        test_cases = [
            ("ValueError: invalid literal", "ValueError"),
            ("KeyError: 'missing_key'", "KeyError"),
            ("AttributeError: 'NoneType' object has no attribute", "AttributeError"),
            ("ImportError: No module named 'missing'", "ImportError"),
            ("RuntimeError: Something went wrong", "RuntimeError"),
        ]

        for log_content, expected_type in test_cases:
            analyzer = LogAnalyzer(log_content)
            analyzer.parse_log(log_content)
            error_type = analyzer.identify_error_type()
            assert error_type == expected_type

    def test_identify_javascript_error_types(self):
        """Test identifying JavaScript error types."""
        log_content = """
TypeError: Cannot read property 'length' of undefined
    at someFunction (app.js:10:5)
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        error_type = analyzer.identify_error_type()

        assert error_type == "TypeError"

    def test_identify_unknown_error_type(self):
        """Test handling logs without clear error type."""
        log_content = "Some random log output without errors"
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        error_type = analyzer.identify_error_type()

        assert error_type == "Unknown"


class TestRootCauseExtraction:
    """Test root cause location extraction."""

    def test_extract_root_cause_filters_library_code(self):
        """Test that root cause extraction filters out library code."""
        log_content = """
Traceback (most recent call last):
  File "/usr/lib/python3.11/site-packages/django/core/handlers/base.py", line 55, in inner
    response = get_response(request)
  File "/usr/lib/python3.11/site-packages/django/core/handlers/exception.py", line 47, in inner
    response = response_for_exception(request, exc)
  File "myproject/views.py", line 120, in my_view
    result = process_request(request)
  File "myproject/utils/processor.py", line 45, in process_request
    data = json.loads(invalid_json)
json.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        root_cause = analyzer.extract_root_cause()

        # Should identify first project file, not library
        assert "myproject" in root_cause["file"]
        assert root_cause["file"] == "myproject/views.py"

    def test_extract_root_cause_no_project_files(self):
        """Test root cause extraction when only library files present."""
        log_content = """
Traceback (most recent call last):
  File "/usr/lib/python3.11/urllib/request.py", line 123, in urlopen
    return opener.open(url, data, timeout)
ConnectionError: Network is unreachable
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        root_cause = analyzer.extract_root_cause()

        # Should return first frame when no project files found
        assert "/usr/lib/python3.11/urllib/request.py" in root_cause["file"]
        assert root_cause["line"] == 123

    def test_extract_root_cause_no_stack_trace(self):
        """Test root cause extraction when no stack trace exists."""
        log_content = "Simple error message without stack trace"
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        root_cause = analyzer.extract_root_cause()

        assert root_cause["file"] is None
        assert root_cause["line"] is None


class TestLogTruncation:
    """Test log truncation functionality."""

    def test_truncate_log_default_200_lines(self):
        """Test truncating log to last 200 lines by default."""
        # Create log with 300 lines
        lines = [f"Line {i}" for i in range(300)]
        log_content = "\n".join(lines)

        analyzer = LogAnalyzer(log_content)
        truncated = analyzer.truncate_log()
        truncated_lines = truncated.split("\n")

        # Should keep last 200 lines plus truncation marker
        assert "... [Log truncated" in truncated
        assert "Line 299" in truncated
        assert "Line 0" not in truncated
        # Truncation marker + 200 lines = 201 (or close)
        assert len(truncated_lines) <= 210  # Some tolerance for marker formatting

    def test_truncate_log_custom_max_lines(self):
        """Test truncating log with custom max_lines parameter."""
        lines = [f"Line {i}" for i in range(100)]
        log_content = "\n".join(lines)

        analyzer = LogAnalyzer(log_content)
        truncated = analyzer.truncate_log(max_lines=50)

        assert "Line 99" in truncated
        assert "Line 0" not in truncated
        assert "... [Log truncated" in truncated

    def test_truncate_log_no_truncation_needed(self):
        """Test that short logs are not truncated."""
        log_content = "Short log\nJust a few lines\nNo truncation needed"

        analyzer = LogAnalyzer(log_content)
        truncated = analyzer.truncate_log(max_lines=200)

        assert "... [Log truncated" not in truncated
        assert truncated == log_content

    def test_truncate_log_exact_boundary(self):
        """Test truncation at exact boundary (200 lines)."""
        lines = [f"Line {i}" for i in range(200)]
        log_content = "\n".join(lines)

        analyzer = LogAnalyzer(log_content)
        truncated = analyzer.truncate_log(max_lines=200)

        # Should not truncate when exactly at limit
        assert "... [Log truncated" not in truncated


class TestLogAnalyzerEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_log_content(self):
        """Test handling empty log content."""
        analyzer = LogAnalyzer("")
        analyzer.parse_log("")

        assert analyzer.extract_stack_traces() == []
        assert analyzer.identify_error_type() == "Unknown"
        assert analyzer.extract_root_cause()["file"] is None

    def test_malformed_stack_trace(self):
        """Test handling malformed stack traces."""
        log_content = """
Traceback (most recent call last):
  File "broken.py", line invalid, in func
This is not a valid stack trace format
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)

        # Should not crash, return what it can parse
        stack_traces = analyzer.extract_stack_traces()
        assert len(stack_traces) >= 0  # Should handle gracefully

    def test_mixed_language_stack_traces(self):
        """Test log with multiple language stack traces."""
        log_content = """
First Python error:
Traceback (most recent call last):
  File "script.py", line 10, in main
    raise ValueError("python error")
ValueError: python error

Then JavaScript error:
Error: JavaScript error
    at Object.<anonymous> (app.js:20:10)
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        stack_traces = analyzer.extract_stack_traces()

        # Should find both stack traces
        assert len(stack_traces) >= 2

    def test_unicode_in_logs(self):
        """Test handling logs with unicode characters."""
        log_content = """
Traceback (most recent call last):
  File "test.py", line 5, in test
    raise ValueError("错误: Unicode 字符")
ValueError: 错误: Unicode 字符
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        error_type = analyzer.identify_error_type()

        assert error_type == "ValueError"

    def test_very_long_single_line(self):
        """Test handling very long single lines in logs."""
        long_line = "A" * 10000
        log_content = f"""
Some context
{long_line}
Traceback (most recent call last):
  File "test.py", line 10, in func
    raise Exception("error")
Exception: error
"""
        analyzer = LogAnalyzer(log_content)
        analyzer.parse_log(log_content)
        stack_traces = analyzer.extract_stack_traces()

        # Should handle long lines without crashing
        assert len(stack_traces) == 1
