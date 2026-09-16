"""Reproduction environment setup and test execution agents.

Based on SYSTEM_DESIGN.md Section 5: Reproduction Agent
Implements Task 4.x: Reproduction agent components.
"""

from swe_agent.agents.reproduction.detector import (
    ProjectTypeDetector,
    TestFrameworkDetector,
    TestCommandInferrer,
    DependencyInstallDetector,
)
from swe_agent.agents.reproduction.agent import ReproductionAgent

__all__ = [
    "ProjectTypeDetector",
    "TestFrameworkDetector",
    "TestCommandInferrer",
    "DependencyInstallDetector",
    "ReproductionAgent",
]
