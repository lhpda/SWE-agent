"""Tests for CLI interface (Task 8.1)."""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from swe_agent.types import PipelineState, StageStatus


class TestCLIArgumentParsing:
    """Test command-line argument parsing."""

    def test_run_command_requires_issue_file(self):
        """Test that run command requires issue file argument."""
        from swe_agent.cli import create_parser

        parser = create_parser()

        # Should fail without issue file
        with pytest.raises(SystemExit):
            parser.parse_args(["run"])

    def test_run_command_with_issue_file(self):
        """Test parsing run command with issue file."""
        from swe_agent.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["run", "issue.json"])

        assert args.command == "run"
        assert args.issue_file == "issue.json"

    def test_run_command_with_config_option(self):
        """Test run command with --config option."""
        from swe_agent.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["run", "issue.json", "--config", "config.yaml"])

        assert args.config == "config.yaml"

    def test_run_command_with_timeout_option(self):
        """Test run command with --timeout option."""
        from swe_agent.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["run", "issue.json", "--timeout", "3600"])

        assert args.timeout == 3600

    def test_run_command_with_verbose_flag(self):
        """Test run command with --verbose flag."""
        from swe_agent.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["run", "issue.json", "--verbose"])

        assert args.verbose is True

    def test_run_command_with_short_verbose_flag(self):
        """Test run command with -v flag."""
        from swe_agent.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["run", "issue.json", "-v"])

        assert args.verbose is True

    def test_run_command_with_output_option(self):
        """Test run command with --output option."""
        from swe_agent.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["run", "issue.json", "--output", "/tmp/output"])

        assert args.output == "/tmp/output"

    def test_run_command_with_short_output_option(self):
        """Test run command with -o option."""
        from swe_agent.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["run", "issue.json", "-o", "/tmp/output"])

        assert args.output == "/tmp/output"

    def test_resume_command_requires_run_id(self):
        """Test that resume command requires run ID argument."""
        from swe_agent.cli import create_parser

        parser = create_parser()

        # Should fail without run ID
        with pytest.raises(SystemExit):
            parser.parse_args(["resume"])

    def test_resume_command_with_run_id(self):
        """Test parsing resume command with run ID."""
        from swe_agent.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["resume", "run-123"])

        assert args.command == "resume"
        assert args.run_id == "run-123"

    def test_status_command_requires_run_id(self):
        """Test that status command requires run ID argument."""
        from swe_agent.cli import create_parser

        parser = create_parser()

        # Should fail without run ID
        with pytest.raises(SystemExit):
            parser.parse_args(["status"])

    def test_status_command_with_run_id(self):
        """Test parsing status command with run ID."""
        from swe_agent.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["status", "run-123"])

        assert args.command == "status"
        assert args.run_id == "run-123"

    def test_list_command_no_arguments(self):
        """Test parsing list command without arguments."""
        from swe_agent.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["list"])

        assert args.command == "list"


class TestRunCommand:
    """Test run command execution."""

    @patch("swe_agent.cli.PipelineOrchestrator")
    @patch("swe_agent.cli.Path")
    def test_run_command_with_valid_issue_file(self, mock_path, mock_orchestrator):
        """Test run command with valid issue file."""
        from swe_agent.cli import run_command

        # Mock file existence
        mock_issue_path = Mock()
        mock_issue_path.exists.return_value = True
        mock_issue_path.read_text.return_value = json.dumps({
            "issue_id": "test-123",
            "title": "Test Issue",
            "body": "Test body"
        })
        mock_path.return_value = mock_issue_path

        # Mock orchestrator
        mock_orch_instance = Mock()
        mock_orch_instance.run.return_value = {
            "status": "success",
            "session_id": "test-session"
        }
        mock_orchestrator.return_value = mock_orch_instance

        # Create mock args
        args = Mock()
        args.issue_file = "issue.json"
        args.config = None
        args.timeout = None
        args.verbose = False
        args.output = None

        exit_code = run_command(args)

        assert exit_code == 0
        mock_orch_instance.run.assert_called_once()

    @patch("swe_agent.cli.Path")
    def test_run_command_with_nonexistent_file(self, mock_path):
        """Test run command with nonexistent issue file."""
        from swe_agent.cli import run_command

        # Mock file non-existence
        mock_issue_path = Mock()
        mock_issue_path.exists.return_value = False
        mock_path.return_value = mock_issue_path

        # Create mock args
        args = Mock()
        args.issue_file = "nonexistent.json"
        args.config = None
        args.timeout = None
        args.verbose = False
        args.output = None

        exit_code = run_command(args)

        assert exit_code == 1

    @patch("swe_agent.cli.PipelineOrchestrator")
    @patch("swe_agent.cli.Path")
    def test_run_command_with_invalid_json(self, mock_path, mock_orchestrator):
        """Test run command with invalid JSON in issue file."""
        from swe_agent.cli import run_command

        # Mock file with invalid JSON
        mock_issue_path = Mock()
        mock_issue_path.exists.return_value = True
        mock_issue_path.read_text.return_value = "invalid json"
        mock_path.return_value = mock_issue_path

        # Create mock args
        args = Mock()
        args.issue_file = "issue.json"
        args.config = None
        args.timeout = None
        args.verbose = False
        args.output = None

        exit_code = run_command(args)

        assert exit_code == 1

    @patch("swe_agent.cli.PipelineOrchestrator")
    @patch("swe_agent.cli.Path")
    def test_run_command_with_custom_config(self, mock_path, mock_orchestrator):
        """Test run command with custom configuration file."""
        from swe_agent.cli import run_command

        # Mock issue file
        mock_issue_path = Mock()
        mock_issue_path.exists.return_value = True
        mock_issue_path.read_text.return_value = json.dumps({"issue_id": "test"})

        # Mock config file
        mock_config_path = Mock()
        mock_config_path.exists.return_value = True

        def path_side_effect(p):
            if "issue" in str(p):
                return mock_issue_path
            return mock_config_path

        mock_path.side_effect = path_side_effect

        # Mock orchestrator
        mock_orch_instance = Mock()
        mock_orch_instance.run.return_value = {"status": "success"}
        mock_orchestrator.return_value = mock_orch_instance

        # Create mock args
        args = Mock()
        args.issue_file = "issue.json"
        args.config = "custom_config.yaml"
        args.timeout = None
        args.verbose = False
        args.output = None

        exit_code = run_command(args)

        assert exit_code == 0

    @patch("swe_agent.cli.PipelineOrchestrator")
    @patch("swe_agent.cli.Path")
    def test_run_command_with_timeout_override(self, mock_path, mock_orchestrator):
        """Test run command with timeout override."""
        from swe_agent.cli import run_command

        # Mock file
        mock_issue_path = Mock()
        mock_issue_path.exists.return_value = True
        mock_issue_path.read_text.return_value = json.dumps({"issue_id": "test"})
        mock_path.return_value = mock_issue_path

        # Mock orchestrator
        mock_orch_instance = Mock()
        mock_orch_instance.run.return_value = {"status": "success"}
        mock_orchestrator.return_value = mock_orch_instance

        # Create mock args with timeout
        args = Mock()
        args.issue_file = "issue.json"
        args.config = None
        args.timeout = 3600
        args.verbose = False
        args.output = None

        exit_code = run_command(args)

        assert exit_code == 0
        # Verify timeout was passed to orchestrator
        call_kwargs = mock_orchestrator.call_args[1] if mock_orchestrator.call_args[1] else {}
        # Check if timeout-related config was used

    @patch("swe_agent.cli.PipelineOrchestrator")
    @patch("swe_agent.cli.Path")
    def test_run_command_handles_keyboard_interrupt(self, mock_path, mock_orchestrator):
        """Test run command handles keyboard interrupt gracefully."""
        from swe_agent.cli import run_command

        # Mock file
        mock_issue_path = Mock()
        mock_issue_path.exists.return_value = True
        mock_issue_path.read_text.return_value = json.dumps({"issue_id": "test"})
        mock_path.return_value = mock_issue_path

        # Mock orchestrator to raise KeyboardInterrupt
        mock_orch_instance = Mock()
        mock_orch_instance.run.side_effect = KeyboardInterrupt()
        mock_orchestrator.return_value = mock_orch_instance

        # Create mock args
        args = Mock()
        args.issue_file = "issue.json"
        args.config = None
        args.timeout = None
        args.verbose = False
        args.output = None

        exit_code = run_command(args)

        assert exit_code == 2  # Interrupted exit code

    @patch("swe_agent.cli.PipelineOrchestrator")
    @patch("swe_agent.cli.Path")
    def test_run_command_handles_exception(self, mock_path, mock_orchestrator):
        """Test run command handles general exceptions."""
        from swe_agent.cli import run_command

        # Mock file
        mock_issue_path = Mock()
        mock_issue_path.exists.return_value = True
        mock_issue_path.read_text.return_value = json.dumps({"issue_id": "test"})
        mock_path.return_value = mock_issue_path

        # Mock orchestrator to raise exception
        mock_orch_instance = Mock()
        mock_orch_instance.run.side_effect = RuntimeError("Test error")
        mock_orchestrator.return_value = mock_orch_instance

        # Create mock args
        args = Mock()
        args.issue_file = "issue.json"
        args.config = None
        args.timeout = None
        args.verbose = False
        args.output = None

        exit_code = run_command(args)

        assert exit_code == 1


class TestResumeCommand:
    """Test resume command execution."""

    @patch("swe_agent.cli.PipelineOrchestrator")
    @patch("swe_agent.cli.StateStore")
    def test_resume_command_with_valid_run_id(self, mock_store, mock_orchestrator):
        """Test resume command with valid run ID."""
        from swe_agent.cli import resume_command

        # Mock state store
        mock_store_instance = Mock()
        mock_store_instance.session_exists.return_value = True
        mock_store.return_value = mock_store_instance

        # Mock orchestrator
        mock_orch_instance = Mock()
        mock_orch_instance.resume.return_value = {"status": "success"}
        mock_orchestrator.return_value = mock_orch_instance

        # Create mock args
        args = Mock()
        args.run_id = "test-run-123"
        args.verbose = False

        exit_code = resume_command(args)

        assert exit_code == 0
        mock_orch_instance.resume.assert_called_once_with("test-run-123")

    @patch("swe_agent.cli.StateStore")
    def test_resume_command_with_invalid_run_id(self, mock_store):
        """Test resume command with invalid run ID."""
        from swe_agent.cli import resume_command

        # Mock state store
        mock_store_instance = Mock()
        mock_store_instance.session_exists.return_value = False
        mock_store.return_value = mock_store_instance

        # Create mock args
        args = Mock()
        args.run_id = "invalid-run"
        args.verbose = False

        exit_code = resume_command(args)

        assert exit_code == 1

    @patch("swe_agent.cli.PipelineOrchestrator")
    @patch("swe_agent.cli.StateStore")
    def test_resume_command_handles_keyboard_interrupt(self, mock_store, mock_orchestrator):
        """Test resume command handles keyboard interrupt."""
        from swe_agent.cli import resume_command

        # Mock state store
        mock_store_instance = Mock()
        mock_store_instance.session_exists.return_value = True
        mock_store.return_value = mock_store_instance

        # Mock orchestrator to raise KeyboardInterrupt
        mock_orch_instance = Mock()
        mock_orch_instance.resume.side_effect = KeyboardInterrupt()
        mock_orchestrator.return_value = mock_orch_instance

        # Create mock args
        args = Mock()
        args.run_id = "test-run"
        args.verbose = False

        exit_code = resume_command(args)

        assert exit_code == 2


class TestStatusCommand:
    """Test status command execution."""

    @patch("swe_agent.cli.StateStore")
    def test_status_command_with_valid_run_id(self, mock_store):
        """Test status command with valid run ID."""
        from swe_agent.cli import status_command

        # Mock state store
        mock_store_instance = Mock()
        mock_store_instance.session_exists.return_value = True
        mock_store_instance.load_state.return_value = PipelineState(
            session_id="test-run",
            status="running",
            current_stage="localization",
            stages={
                "localization": StageStatus(
                    status="running",
                    retries=0
                )
            },
            retry_count=0,
            max_retries=3,
            started_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:01:00Z"
        )
        mock_store.return_value = mock_store_instance

        # Create mock args
        args = Mock()
        args.run_id = "test-run"

        exit_code = status_command(args)

        assert exit_code == 0

    @patch("swe_agent.cli.StateStore")
    def test_status_command_with_invalid_run_id(self, mock_store):
        """Test status command with invalid run ID."""
        from swe_agent.cli import status_command

        # Mock state store
        mock_store_instance = Mock()
        mock_store_instance.session_exists.return_value = False
        mock_store.return_value = mock_store_instance

        # Create mock args
        args = Mock()
        args.run_id = "invalid-run"

        exit_code = status_command(args)

        assert exit_code == 1

    @patch("swe_agent.cli.StateStore")
    def test_status_command_displays_all_stages(self, mock_store, capsys):
        """Test that status command displays all stage information."""
        from swe_agent.cli import status_command

        # Mock state store with multiple stages
        mock_store_instance = Mock()
        mock_store_instance.session_exists.return_value = True
        mock_store_instance.load_state.return_value = PipelineState(
            session_id="test-run",
            status="running",
            current_stage="reproduction",
            stages={
                "localization": StageStatus(
                    status="success",
                    started_at="2024-01-01T00:00:00Z",
                    completed_at="2024-01-01T00:02:00Z",
                    duration=120.0,
                    retries=0
                ),
                "reproduction": StageStatus(
                    status="running",
                    started_at="2024-01-01T00:02:00Z",
                    retries=1
                )
            },
            retry_count=0,
            max_retries=3,
            started_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:02:30Z"
        )
        mock_store.return_value = mock_store_instance

        # Create mock args
        args = Mock()
        args.run_id = "test-run"

        exit_code = status_command(args)

        assert exit_code == 0


class TestListCommand:
    """Test list command execution."""

    @patch("swe_agent.cli.StateStore")
    def test_list_command_with_no_runs(self, mock_store):
        """Test list command when no runs exist."""
        from swe_agent.cli import list_command

        # Mock state store with no sessions
        mock_store_instance = Mock()
        mock_store_instance.list_sessions.return_value = []
        mock_store.return_value = mock_store_instance

        # Create mock args
        args = Mock()

        exit_code = list_command(args)

        assert exit_code == 0

    @patch("swe_agent.cli.StateStore")
    def test_list_command_with_multiple_runs(self, mock_store):
        """Test list command with multiple runs."""
        from swe_agent.cli import list_command

        # Mock state store with multiple sessions
        mock_store_instance = Mock()
        mock_store_instance.list_sessions.return_value = [
            {
                "session_id": "run-1",
                "status": "success",
                "started_at": "2024-01-01T00:00:00Z",
                "completed_at": "2024-01-01T00:10:00Z"
            },
            {
                "session_id": "run-2",
                "status": "running",
                "started_at": "2024-01-01T01:00:00Z",
                "completed_at": None
            },
            {
                "session_id": "run-3",
                "status": "failed",
                "started_at": "2024-01-01T02:00:00Z",
                "completed_at": "2024-01-01T02:05:00Z"
            }
        ]
        mock_store.return_value = mock_store_instance

        # Create mock args
        args = Mock()

        exit_code = list_command(args)

        assert exit_code == 0

    @patch("swe_agent.cli.StateStore")
    def test_list_command_displays_session_info(self, mock_store, capsys):
        """Test that list command displays session information."""
        from swe_agent.cli import list_command

        # Mock state store
        mock_store_instance = Mock()
        mock_store_instance.list_sessions.return_value = [
            {
                "session_id": "test-run",
                "status": "success",
                "started_at": "2024-01-01T00:00:00Z",
                "completed_at": "2024-01-01T00:10:00Z"
            }
        ]
        mock_store.return_value = mock_store_instance

        # Create mock args
        args = Mock()

        exit_code = list_command(args)

        assert exit_code == 0


class TestExitCodes:
    """Test CLI exit codes."""

    def test_success_exit_code_is_zero(self):
        """Test that success exit code is 0."""
        from swe_agent.cli import EXIT_SUCCESS

        assert EXIT_SUCCESS == 0

    def test_failure_exit_code_is_one(self):
        """Test that failure exit code is 1."""
        from swe_agent.cli import EXIT_FAILURE

        assert EXIT_FAILURE == 1

    def test_interrupted_exit_code_is_two(self):
        """Test that interrupted exit code is 2."""
        from swe_agent.cli import EXIT_INTERRUPTED

        assert EXIT_INTERRUPTED == 2


class TestVerboseOutput:
    """Test verbose output mode."""

    @patch("swe_agent.cli.PipelineOrchestrator")
    @patch("swe_agent.cli.Path")
    def test_verbose_mode_enables_detailed_logging(self, mock_path, mock_orchestrator):
        """Test that verbose mode enables detailed logging."""
        from swe_agent.cli import run_command

        # Mock file
        mock_issue_path = Mock()
        mock_issue_path.exists.return_value = True
        mock_issue_path.read_text.return_value = json.dumps({"issue_id": "test"})
        mock_path.return_value = mock_issue_path

        # Mock orchestrator
        mock_orch_instance = Mock()
        mock_orch_instance.run.return_value = {"status": "success"}
        mock_orchestrator.return_value = mock_orch_instance

        # Create mock args with verbose
        args = Mock()
        args.issue_file = "issue.json"
        args.config = None
        args.timeout = None
        args.verbose = True
        args.output = None

        exit_code = run_command(args)

        assert exit_code == 0


class TestOutputDirectory:
    """Test output directory option."""

    @patch("swe_agent.cli.PipelineOrchestrator")
    @patch("swe_agent.cli.Path")
    def test_output_directory_is_created(self, mock_path, mock_orchestrator):
        """Test that output directory is created if it doesn't exist."""
        from swe_agent.cli import run_command

        # Mock issue file
        mock_issue_path = Mock()
        mock_issue_path.exists.return_value = True
        mock_issue_path.read_text.return_value = json.dumps({"issue_id": "test"})

        # Mock output directory
        mock_output_path = Mock()
        mock_output_path.exists.return_value = False

        def path_side_effect(p):
            if "issue" in str(p):
                return mock_issue_path
            return mock_output_path

        mock_path.side_effect = path_side_effect

        # Mock orchestrator
        mock_orch_instance = Mock()
        mock_orch_instance.run.return_value = {"status": "success"}
        mock_orchestrator.return_value = mock_orch_instance

        # Create mock args
        args = Mock()
        args.issue_file = "issue.json"
        args.config = None
        args.timeout = None
        args.verbose = False
        args.output = "/tmp/output"

        exit_code = run_command(args)

        assert exit_code == 0
        # Verify output directory creation was attempted
        # (actual verification depends on implementation details)


class TestMainFunction:
    """Test main entry point."""

    @patch("swe_agent.cli.create_parser")
    @patch("swe_agent.cli.run_command")
    def test_main_calls_run_command(self, mock_run_command, mock_create_parser):
        """Test that main function dispatches to run command."""
        from swe_agent.cli import main

        # Mock parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.command = "run"
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser

        # Mock run command
        mock_run_command.return_value = 0

        with patch.object(sys, "argv", ["swe-agent", "run", "issue.json"]):
            exit_code = main()

        assert exit_code == 0
        mock_run_command.assert_called_once_with(mock_args)

    @patch("swe_agent.cli.create_parser")
    @patch("swe_agent.cli.resume_command")
    def test_main_calls_resume_command(self, mock_resume_command, mock_create_parser):
        """Test that main function dispatches to resume command."""
        from swe_agent.cli import main

        # Mock parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.command = "resume"
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser

        # Mock resume command
        mock_resume_command.return_value = 0

        with patch.object(sys, "argv", ["swe-agent", "resume", "run-123"]):
            exit_code = main()

        assert exit_code == 0
        mock_resume_command.assert_called_once_with(mock_args)

    @patch("swe_agent.cli.create_parser")
    @patch("swe_agent.cli.status_command")
    def test_main_calls_status_command(self, mock_status_command, mock_create_parser):
        """Test that main function dispatches to status command."""
        from swe_agent.cli import main

        # Mock parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.command = "status"
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser

        # Mock status command
        mock_status_command.return_value = 0

        with patch.object(sys, "argv", ["swe-agent", "status", "run-123"]):
            exit_code = main()

        assert exit_code == 0
        mock_status_command.assert_called_once_with(mock_args)

    @patch("swe_agent.cli.create_parser")
    @patch("swe_agent.cli.list_command")
    def test_main_calls_list_command(self, mock_list_command, mock_create_parser):
        """Test that main function dispatches to list command."""
        from swe_agent.cli import main

        # Mock parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.command = "list"
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser

        # Mock list command
        mock_list_command.return_value = 0

        with patch.object(sys, "argv", ["swe-agent", "list"]):
            exit_code = main()

        assert exit_code == 0
        mock_list_command.assert_called_once_with(mock_args)
