"""Command-line interface for SWE Agent.

This module provides the CLI for running, resuming, and monitoring SWE Agent pipeline executions.

Commands:
    run: Execute pipeline on an issue
    resume: Resume a previous run
    status: Check run status
    list: List all runs

Exit codes:
    0: Success
    1: Failure
    2: Interrupted (Ctrl+C)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Fix Windows console encoding
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

from swe_agent.config import Config, load_config
from swe_agent.logging import get_logger
from swe_agent.storage import StateStore
from swe_agent.types import PipelineState, IssueContext, RepositoryContext
from swe_agent.orchestrator.pipeline import PipelineOrchestrator

logger = get_logger(__name__)

# Exit codes
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_INTERRUPTED = 2


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser.

    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="swe-agent",
        description="SWE Agent - Automated Software Engineering Agent for Bug Fixing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run pipeline on an issue",
        description="Execute the SWE Agent pipeline on a GitHub issue",
    )
    run_parser.add_argument(
        "issue_file",
        type=str,
        help="Path to issue JSON file",
    )
    run_parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to configuration file",
    )
    run_parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=None,
        help="Override global timeout in seconds",
    )
    run_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    run_parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output directory for results",
    )

    # Resume command
    resume_parser = subparsers.add_parser(
        "resume",
        help="Resume a previous run",
        description="Resume a previously interrupted or failed pipeline execution",
    )
    resume_parser.add_argument(
        "run_id",
        type=str,
        help="Run ID (session ID) to resume",
    )
    resume_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Check run status",
        description="Display the current status of a pipeline execution",
    )
    status_parser.add_argument(
        "run_id",
        type=str,
        help="Run ID (session ID) to check",
    )

    # List command
    list_parser = subparsers.add_parser(
        "list",
        help="List all runs",
        description="List all pipeline execution runs",
    )

    return parser


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity level.

    Args:
        verbose: Enable verbose logging
    """
    import logging

    if verbose:
        logging.getLogger("swe_agent").setLevel(logging.DEBUG)
    else:
        logging.getLogger("swe_agent").setLevel(logging.INFO)


def load_issue_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Load and parse issue JSON file.

    Args:
        file_path: Path to issue file

    Returns:
        Issue data dictionary or None if error
    """
    issue_path = Path(file_path)

    if not issue_path.exists():
        print(f"Error: Issue file not found: {file_path}", file=sys.stderr)
        return None

    try:
        content = issue_path.read_text(encoding="utf-8")
        issue_data = json.loads(content)
        return issue_data
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in issue file: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error reading issue file: {e}", file=sys.stderr)
        return None


def load_config_file(config_path: Optional[str]) -> Config:
    """Load configuration from file or use defaults.

    Args:
        config_path: Path to config file, or None for defaults

    Returns:
        Configuration object
    """
    if config_path:
        config_file = Path(config_path)
        if not config_file.exists():
            print(f"Warning: Config file not found: {config_path}, using defaults", file=sys.stderr)
            return load_config()

        try:
            return load_config(config_path)
        except Exception as e:
            print(f"Warning: Failed to load config file: {e}, using defaults", file=sys.stderr)
            return load_config()

    return load_config()


def print_progress(message: str, status: str = "info") -> None:
    """Print formatted progress message.

    Args:
        message: Message to display
        status: Status type (info, success, error, warning)
    """
    symbols = {
        "info": "→",
        "success": "✓",
        "error": "✗",
        "warning": "⚠",
    }

    symbol = symbols.get(status, "→")
    print(f"{symbol} {message}")


def print_stage_status(stage_name: str, stage_status: Any) -> None:
    """Print formatted stage status.

    Args:
        stage_name: Name of the stage
        stage_status: StageStatus object
    """
    status_str = stage_status.status
    status_symbols = {
        "pending": "⋯",
        "running": "→",
        "success": "✓",
        "failed": "✗",
        "skipped": "−",
    }

    symbol = status_symbols.get(status_str, "?")

    # Format timing info
    timing = ""
    if stage_status.duration is not None:
        timing = f" ({stage_status.duration:.1f}s)"
    elif stage_status.started_at:
        timing = " (running)"

    # Format retry info
    retry_info = ""
    if stage_status.retries > 0:
        retry_info = f" [retries: {stage_status.retries}]"

    print(f"  {symbol} {stage_name}: {status_str}{timing}{retry_info}")


def run_command(args: argparse.Namespace) -> int:
    """Execute run command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code
    """
    setup_logging(args.verbose)

    # Load issue file
    issue_data = load_issue_file(args.issue_file)
    if issue_data is None:
        return EXIT_FAILURE

    # Load configuration
    config = load_config_file(args.config)

    # Override timeout if specified
    if args.timeout:
        config.global_timeout = args.timeout

    # Create output directory if specified
    if args.output:
        output_path = Path(args.output)
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Error: Failed to create output directory: {e}", file=sys.stderr)
            return EXIT_FAILURE

    # Initialize storage
    storage = StateStore(base_path=config.storage_base_path)

    # Build IssueContext
    try:
        issue = IssueContext(
            issue_id=str(issue_data.get("issue_number", "unknown")),
            title=issue_data.get("title", ""),
            body=issue_data.get("body", ""),
            parsed=issue_data.get("code_context", {}),
            metadata={
                "labels": issue_data.get("labels", []),
                "repo": issue_data.get("repo", ""),
            },
        )
    except Exception as e:
        print(f"Error: Failed to parse issue data: {e}", file=sys.stderr)
        return EXIT_FAILURE

    # Build RepositoryContext (use current directory as default)
    try:
        repo_path = str(Path(issue_data.get("repo_path", ".")).resolve())
        if not Path(repo_path).is_dir():
            raise ValueError(f"Repository directory does not exist: {repo_path}")
        repository = RepositoryContext(
            path=repo_path,
            git={"branch": "main", "commit": "HEAD"},
            project_type="python",
            test_framework="pytest",
            dependencies={},
        )
    except Exception as e:
        print(f"Error: Failed to create repository context: {e}", file=sys.stderr)
        return EXIT_FAILURE

    # Initialize orchestrator
    try:
        orchestrator = PipelineOrchestrator(
            issue=issue,
            repository=repository,
            state_store=storage,
            global_timeout=config.global_timeout,
            config=config,
        )
    except Exception as e:
        print(f"Error: Failed to initialize orchestrator: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return EXIT_FAILURE

    # Run pipeline
    try:
        print_progress("Starting SWE Agent pipeline", "info")
        print_progress(f"Issue: {issue.title}", "info")
        print_progress(f"Session ID: {orchestrator.session_id}", "info")

        result = orchestrator.run()

        if result.status == "success":
            print_progress("Pipeline completed successfully", "success")
            print(f"\nSession ID: {result.session_id}")

            if result.final_patch:
                print(f"Final patch generated")
                output_dir = (
                    Path(args.output)
                    if args.output
                    else storage.get_session_path(result.session_id)
                )
                patch_file = output_dir / "final_patch.diff"
                patch_file.write_text(
                    result.final_patch.get("unified_diff", ""), encoding="utf-8", newline=""
                )
                print(f"Patch saved to: {patch_file}")

            return EXIT_SUCCESS
        else:
            print_progress("Pipeline failed", "error")
            if result.error:
                print(f"Error: {result.error.message}")
            return EXIT_FAILURE

    except KeyboardInterrupt:
        print_progress("\nPipeline interrupted by user", "warning")
        return EXIT_INTERRUPTED
    except Exception as e:
        print_progress(f"Pipeline error: {e}", "error")
        logger.exception("Unexpected error during pipeline execution")
        import traceback

        traceback.print_exc()
        return EXIT_FAILURE


def resume_command(args: argparse.Namespace) -> int:
    """Execute resume command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code
    """
    setup_logging(args.verbose)

    # Initialize storage
    storage = StateStore(base_path=load_config().storage_base_path)

    # Check if session exists
    if not storage.session_exists(args.run_id):
        print(f"Error: Run ID not found: {args.run_id}", file=sys.stderr)
        return EXIT_FAILURE

    # Resume pipeline
    try:
        print_progress(f"Resuming pipeline: {args.run_id}", "info")

        orchestrator = PipelineOrchestrator.resume(args.run_id, storage)
        result = orchestrator.run()

        if result.status == "success":
            print_progress("Pipeline resumed and completed successfully", "success")
            return EXIT_SUCCESS
        else:
            print_progress("Pipeline failed", "error")
            if result.error:
                print(f"Error: {result.error.message}")
            return EXIT_FAILURE

    except KeyboardInterrupt:
        print_progress("\nPipeline interrupted by user", "warning")
        return EXIT_INTERRUPTED
    except Exception as e:
        print_progress(f"Pipeline error: {e}", "error")
        logger.exception("Unexpected error during pipeline resumption")
        return EXIT_FAILURE


def status_command(args: argparse.Namespace) -> int:
    """Execute status command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code
    """
    # Initialize storage
    storage = StateStore(base_path=load_config().storage_base_path)

    # Check if session exists
    if not storage.session_exists(args.run_id):
        print(f"Error: Run ID not found: {args.run_id}", file=sys.stderr)
        return EXIT_FAILURE

    # Load state
    try:
        state = storage.load_state(args.run_id)

        print(f"\nRun ID: {state.session_id}")
        print(f"Status: {state.status}")

        if state.current_stage:
            print(f"Current Stage: {state.current_stage}")

        print(f"Started: {state.started_at}")

        if state.completed_at:
            print(f"Completed: {state.completed_at}")

        print(f"\nStages:")
        for stage_name, stage_status in state.stages.items():
            print_stage_status(stage_name, stage_status)

        if state.error:
            print(f"\nError: {state.error.message}")
            if state.error.details:
                print(f"Details: {state.error.details}")

        return EXIT_SUCCESS

    except Exception as e:
        print(f"Error: Failed to load status: {e}", file=sys.stderr)
        logger.exception("Error loading pipeline state")
        return EXIT_FAILURE


def list_command(args: argparse.Namespace) -> int:
    """Execute list command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code
    """
    # Initialize storage
    storage = StateStore(base_path=load_config().storage_base_path)

    # List all sessions
    try:
        sessions = storage.list_sessions()

        if not sessions:
            print("No runs found.")
            return EXIT_SUCCESS

        print(f"\nFound {len(sessions)} run(s):\n")

        # Print header
        print(f"{'Session ID':<40} {'Status':<15} {'Started':<25} {'Completed':<25}")
        print("-" * 105)

        # Print sessions
        for session in sessions:
            if isinstance(session, str):
                metadata = storage.load_metadata(session) or {}
                history = metadata.get("history", [])
                session = {
                    "session_id": session,
                    "status": metadata.get("current_state", "unknown"),
                    "started_at": history[0]["timestamp"] if history else "N/A",
                    "completed_at": metadata.get("completed_at"),
                }
            session_id = session.get("session_id", "N/A")
            status = session.get("status", "N/A")
            started = session.get("started_at", "N/A")
            completed = session.get("completed_at", "N/A") or "-"

            print(f"{session_id:<40} {status:<15} {started:<25} {completed:<25}")

        return EXIT_SUCCESS

    except Exception as e:
        print(f"Error: Failed to list sessions: {e}", file=sys.stderr)
        logger.exception("Error listing sessions")
        return EXIT_FAILURE


def main() -> int:
    """Main entry point for CLI.

    Returns:
        Exit code
    """
    parser = create_parser()
    args = parser.parse_args()

    # Dispatch to appropriate command
    if args.command == "run":
        return run_command(args)
    elif args.command == "resume":
        return resume_command(args)
    elif args.command == "status":
        return status_command(args)
    elif args.command == "list":
        return list_command(args)
    else:
        parser.print_help()
        return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())
