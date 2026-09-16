# E2E Test Dataset Documentation

This directory contains end-to-end test fixtures and test suites for the SWE Agent project.

## Overview

The E2E test dataset is designed to validate the complete SWE Agent pipeline from issue parsing through localization, reproduction, patch generation, and validation. Test cases are organized by complexity level and cover multiple programming languages.

## Directory Structure

```
tests/
├── fixtures/
│   ├── issues/          # Issue JSON fixtures (10 test cases)
│   └── repos/           # Test repository setups (to be populated)
└── e2e/
    ├── __init__.py
    └── test_e2e_simple.py   # E2E test suite
```

## Test Case Categories

### Simple Bugs (3 cases)

Simple bugs have clear error messages, specific stack traces, and straightforward fixes. These test the agent's ability to handle common programming errors.

| ID | File | Language | Description |
|---|---|---|---|
| simple-001 | `simple_01_python_division_by_zero.json` | Python | Division by zero in calculate_average function |
| simple-002 | `simple_02_js_null_reference.json` | JavaScript | Null reference error accessing object property |
| simple-003 | `simple_03_python_off_by_one.json` | Python | IndexError due to off-by-one array access |

**Characteristics:**
- Clear stack traces with file and line numbers
- Single-file fixes
- Estimated fix time: 1-5 minutes
- Test framework coverage: pytest, jest

### Medium Complexity (4 cases)

Medium complexity bugs involve multiple components, concurrency issues, security vulnerabilities, or require understanding broader context.

| ID | File | Language | Description |
|---|---|---|---|
| medium-001 | `medium_01_python_async_race_condition.json` | Python | Race condition in async cache causing duplicate backend calls |
| medium-002 | `medium_02_js_memory_leak.json` | JavaScript | Memory leak from improper event listener cleanup |
| medium-003 | `medium_03_python_sql_injection.json` | Python | SQL injection vulnerability in user search |
| medium-004 | `medium_04_js_promise_unhandled_rejection.json` | JavaScript | Unhandled promise rejection in async data fetcher |

**Characteristics:**
- Involve async/concurrency, memory management, or security
- May require understanding multiple related functions
- Estimated fix time: 10-20 minutes
- Require deeper code analysis

### Complex Scenarios (2 cases)

Complex scenarios involve distributed systems, multiple interacting components, or sophisticated security vulnerabilities.

| ID | File | Language | Description |
|---|---|---|---|
| complex-001 | `complex_01_python_deadlock.json` | Python | Distributed transaction deadlock in payment processor |
| complex-002 | `complex_02_js_jwt_vulnerability.json` | JavaScript | Multiple JWT authentication vulnerabilities |

**Characteristics:**
- Multi-component systems (database transactions, authentication)
- Require understanding of distributed systems or security concepts
- Estimated fix time: 30-60 minutes
- May need external resources (databases, concurrency testing)

### Negative Cases (1 case)

Negative cases are intentionally vague or missing critical information. The agent should fail gracefully on these.

| ID | File | Language | Description |
|---|---|---|---|
| negative-001 | `negative_01_vague_performance.json` | Python | Vague performance complaint without specifics |

**Characteristics:**
- Missing stack traces or file locations
- Vague descriptions without reproduction steps
- No measurable success criteria
- Expected outcome: FAILED with clear explanation

## Issue JSON Schema

Each issue fixture follows this structure:

```json
{
  "issue_id": "unique-id",
  "title": "Brief description",
  "language": "python|javascript|...",
  "complexity": "simple|medium|complex|negative",
  "body": "Full issue description with error messages and stack traces",
  "repository": {
    "type": "python|nodejs|...",
    "test_framework": "pytest|jest|...",
    "test_command": "command to run tests"
  },
  "expected_fix": {
    "file": "path/to/file.py",
    "description": "What needs to be fixed",
    "validation": "How to verify the fix"
  },
  "setup_instructions": [
    "Step 1: Create necessary files",
    "Step 2: Setup test environment"
  ],
  "metadata": {
    "created_at": "2026-09-16",
    "difficulty": "simple|medium|complex|negative",
    "estimated_fix_time": "time estimate",
    "security_issue": true,  // if applicable
    "requires_database": true  // if applicable
  }
}
```

## Language Coverage

The test dataset covers multiple programming languages:

- **Python**: 5 cases (simple: 2, medium: 2, complex: 1)
- **JavaScript**: 5 cases (simple: 1, medium: 2, complex: 1, negative: 1)

Future additions should include:
- Java (medium-high complexity)
- Rust (type system bugs)
- Go (concurrency issues)

## Running Tests

### Run all E2E tests:
```bash
pytest tests/e2e/test_e2e_simple.py -v
```

### Run specific test category:
```bash
# Simple bugs only
pytest tests/e2e/test_e2e_simple.py::TestE2ESimpleBugs -v

# Fixture validation
pytest tests/e2e/test_e2e_simple.py::TestE2EFixtureValidation -v

# Mock pipeline tests
pytest tests/e2e/test_e2e_simple.py::TestE2EMockPipeline -v
```

### Validate all fixtures:
```bash
pytest tests/e2e/test_e2e_simple.py::TestE2EFixtureValidation::test_fixture_json_valid -v
```

## Adding New Test Cases

### Step 1: Create Issue JSON

Create a new JSON file in `tests/fixtures/issues/` following the schema above:

```bash
# Naming convention: {complexity}_{number}_{language}_{short_description}.json
tests/fixtures/issues/medium_05_python_new_bug.json
```

### Step 2: Ensure Required Fields

All required fields must be present:
- `issue_id`, `title`, `body`, `language`, `complexity`
- `repository` with `type`, `test_framework`, `test_command`
- `expected_fix` with `file`, `description`, `validation`
- `setup_instructions` array
- `metadata` with `created_at`, `difficulty`, `estimated_fix_time`

### Step 3: Validate JSON

Run validation tests to ensure the fixture is well-formed:

```bash
pytest tests/e2e/test_e2e_simple.py::TestE2EFixtureValidation -v
```

### Step 4: Add Test Method (Optional)

For important test cases, add a dedicated test method in `TestE2ESimpleBugs` or similar:

```python
def test_medium_05_python_new_bug(self):
    """Test description."""
    issue = load_issue_fixture("medium_05_python_new_bug.json")
    # Add assertions
    assert issue["issue_id"] == "medium-005"
    # TODO: Add full pipeline test once implemented
```

## Success Criteria

### For Simple Bugs:
- **Localization accuracy**: > 90%
- **Patch generation success**: > 85%
- **Average execution time**: < 5 minutes

### For Medium Complexity:
- **Localization accuracy**: > 70%
- **Patch generation success**: > 60%
- **Average execution time**: < 15 minutes

### For Complex Scenarios:
- **Localization accuracy**: > 50%
- **Patch generation success**: > 40%
- **Average execution time**: < 30 minutes

### For Negative Cases:
- **Expected outcome**: FAILED with clear error message
- **Should not**: Produce incorrect patches or false positives
- **Should**: Provide actionable feedback on missing information

## Test Repository Setup

Test repositories should be set up in `tests/fixtures/repos/` with the following structure:

```
tests/fixtures/repos/
├── simple_python_math/       # For simple-001
│   ├── src/
│   │   └── math_utils.py     # With bug
│   ├── tests/
│   │   └── test_math_utils.py
│   └── requirements.txt
├── simple_js_user/           # For simple-002
│   ├── src/
│   │   └── user.js           # With bug
│   ├── tests/
│   │   └── user.test.js
│   └── package.json
└── ...
```

Each repository should:
1. Contain the buggy code matching the issue description
2. Include failing tests that will pass after the fix
3. Have minimal dependencies
4. Be self-contained and reproducible

## Integration with Pipeline

Once `PipelineOrchestrator` is implemented, tests should be updated to:

1. Create test repositories from fixtures
2. Run the full pipeline: `orchestrator.run(issue, repo_path)`
3. Validate the generated patch
4. Verify tests pass after applying the patch
5. Check execution time is within expected range

Example integration test:

```python
def test_simple_bug_full_pipeline(self):
    # Setup test repo
    repo_path = setup_test_repo("simple_python_math")
    
    # Load issue
    issue = load_issue_fixture("simple_01_python_division_by_zero.json")
    
    # Run pipeline
    orchestrator = PipelineOrchestrator(session_id="test-001")
    result = orchestrator.run(issue, repo_path)
    
    # Validate result
    assert result.status == "success"
    assert result.patch is not None
    assert "len(numbers)" in result.patch
    
    # Apply and test
    apply_patch(repo_path, result.patch)
    test_result = run_tests(repo_path)
    assert test_result.passed > 0
    assert test_result.failed == 0
```

## Maintenance

### Periodic Reviews

Review and update test cases quarterly to:
- Add new bug patterns discovered in production
- Update language versions and frameworks
- Refine complexity classifications
- Add edge cases and corner scenarios

### Version Control

All test fixtures are version-controlled. When modifying:
1. Document changes in commit message
2. Update `metadata.created_at` if significantly changed
3. Preserve backward compatibility when possible
4. Add migration notes for breaking changes

## Related Documentation

- [SYSTEM_DESIGN.md](../../SYSTEM_DESIGN.md) - Overall system architecture
- [TASKS.md](../../TASKS.md) - Development task tracking
- [tests/README.md](../README.md) - General testing documentation

## Contact

For questions or suggestions about test cases:
- Review the issue template schema
- Check existing test cases for patterns
- Refer to SYSTEM_DESIGN.md for pipeline stages
