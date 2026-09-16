# SWE Agent Examples

**Version**: 0.1.0  
**Last Updated**: 2026-09-16

---

## Table of Contents

1. [Example 1: Simple Bug Fix (Python)](#example-1-simple-bug-fix-python)
2. [Example 2: Medium Complexity Issue (JavaScript)](#example-2-medium-complexity-issue-javascript)
3. [Example 3: Using Configuration Options](#example-3-using-configuration-options)
4. [Example 4: Resuming a Session](#example-4-resuming-a-session)
5. [Example 5: Debugging Failed Runs](#example-5-debugging-failed-runs)

---

## Example 1: Simple Bug Fix (Python)

### Scenario

A Python application has a division by zero error in a calculator module.

### Issue Description

**GitHub Issue #42**: "Calculator crashes on zero division"

```
Title: Calculator crashes on zero division
Labels: bug

When I try to divide by zero, the calculator crashes instead of handling the error gracefully.

Steps to reproduce:
1. Run: python calculator.py
2. Enter: 10 / 0
3. See error: ZeroDivisionError

Expected: Should display "Error: Cannot divide by zero"
Actual: Program crashes with traceback

Stack trace:
```python
Traceback (most recent call last):
  File "calculator.py", line 45, in calculate
    result = a / b
ZeroDivisionError: division by zero
```
```

### Repository Structure

```
my-calculator/
├── calculator.py
├── tests/
│   └── test_calculator.py
└── requirements.txt
```

### Running SWE Agent

```bash
cd my-calculator

# Run SWE Agent
poetry run swe-agent \
  --issue "https://github.com/username/my-calculator/issues/42" \
  --repo .
```

### Expected Output

```
[2026-09-16 10:00:00] Starting SWE Agent...
[2026-09-16 10:00:01] Session ID: calc-fix-20260916-100000
[2026-09-16 10:00:02] Loading issue #42...
[2026-09-16 10:00:03] Repository detected: Python (pytest)

[2026-09-16 10:00:05] Stage 1/4: Localization
[2026-09-16 10:00:06] Parsing issue for error patterns...
[2026-09-16 10:00:07] Found stack trace: calculator.py:45
[2026-09-16 10:00:10] Searching for relevant code...
[2026-09-16 10:01:30] ✓ Localization complete (90 seconds)
[2026-09-16 10:01:30] Found candidates:
  - calculator.py (confidence: 0.95)
  - tests/test_calculator.py (confidence: 0.60)

[2026-09-16 10:01:31] Stage 2/4: Reproduction
[2026-09-16 10:01:32] Setting up Docker sandbox...
[2026-09-16 10:01:45] Installing dependencies...
[2026-09-16 10:02:15] Running tests...
[2026-09-16 10:02:30] ✓ Reproduction complete (59 seconds)
[2026-09-16 10:02:30] Error reproduced: ZeroDivisionError at calculator.py:45

[2026-09-16 10:02:31] Stage 3/4: Patch Generation
[2026-09-16 10:02:32] Building code context...
[2026-09-16 10:02:45] Generating patch candidates...
[2026-09-16 10:04:30] ✓ Patch generation complete (119 seconds)
[2026-09-16 10:04:30] Generated 3 patch candidates

[2026-09-16 10:04:31] Stage 4/4: Validation
[2026-09-16 10:04:32] Validating patch #1...
[2026-09-16 10:05:15] ✓ Patch #1 passed all tests
[2026-09-16 10:05:15] ✓ Validation complete (44 seconds)

[2026-09-16 10:05:16] ✓ Success!
[2026-09-16 10:05:16] Total execution time: 5 minutes 16 seconds
[2026-09-16 10:05:16] Patch saved to: .swe-agent/sessions/calc-fix-20260916-100000/final_patch.diff
```

### Generated Patch

```diff
--- a/calculator.py
+++ b/calculator.py
@@ -42,7 +42,12 @@ class Calculator:
     def calculate(self, a, b, operation):
         """Perform calculation based on operation."""
         if operation == "divide":
-            result = a / b
+            try:
+                result = a / b
+            except ZeroDivisionError:
+                return "Error: Cannot divide by zero"
         elif operation == "multiply":
             result = a * b
         elif operation == "add":
```

### Applying the Patch

```bash
# Review the patch
cat .swe-agent/sessions/calc-fix-20260916-100000/final_patch.diff

# Apply it
git apply .swe-agent/sessions/calc-fix-20260916-100000/final_patch.diff

# Verify the fix
git diff

# Run tests
pytest tests/

# Commit the fix
git add calculator.py
git commit -m "fix: handle division by zero error

Fixes #42

Co-Authored-By: SWE Agent <swe-agent@example.com>"
git push origin main
```

---

## Example 2: Medium Complexity Issue (JavaScript)

### Scenario

A Node.js API has an authentication bug where expired tokens are still accepted.

### Issue Description

**GitHub Issue #87**: "Expired JWT tokens still grant access"

```
Title: Expired JWT tokens still grant access
Labels: bug, security

Description:
Users can still access protected endpoints even after their JWT tokens expire.

Steps to reproduce:
1. Login and get JWT token (expires in 1 hour)
2. Wait for token to expire
3. Make API request with expired token
4. Request succeeds (should fail with 401)

Error in logs:
TypeError: Cannot read property 'exp' of undefined
  at validateToken (src/auth/middleware.js:23)

Expected: 401 Unauthorized
Actual: 200 OK with valid response
```

### Repository Structure

```
express-api/
├── src/
│   ├── auth/
│   │   ├── middleware.js
│   │   └── token.js
│   └── routes/
│       └── api.js
├── tests/
│   └── auth.test.js
├── package.json
└── jest.config.js
```

### Running SWE Agent

```bash
cd express-api

# Run with custom timeout (this is a more complex issue)
export SWE_AGENT_LOCALIZATION_TIMEOUT=600
export SWE_AGENT_REPRODUCTION_TIMEOUT=900

poetry run swe-agent \
  --issue "https://github.com/username/express-api/issues/87" \
  --repo . \
  --verbose
```

### Expected Output (Verbose Mode)

```
[2026-09-16 11:00:00] [DEBUG] Initializing SWE Agent...
[2026-09-16 11:00:00] [INFO] Session ID: auth-fix-20260916-110000
[2026-09-16 11:00:01] [DEBUG] Loading configuration...
[2026-09-16 11:00:01] [INFO] Config: localization_timeout=600s, reproduction_timeout=900s

[2026-09-16 11:00:02] [INFO] Stage 1/4: Localization
[2026-09-16 11:00:03] [DEBUG] Parsing issue body...
[2026-09-16 11:00:03] [DEBUG] Found error: TypeError at src/auth/middleware.js:23
[2026-09-16 11:00:04] [DEBUG] Calling tool: ripgrep_search
[2026-09-16 11:00:04] [DEBUG] Search pattern: "validateToken"
[2026-09-16 11:00:05] [DEBUG] Found 3 matches
[2026-09-16 11:00:06] [DEBUG] Calling tool: read_file
[2026-09-16 11:00:06] [DEBUG] Reading: src/auth/middleware.js
[2026-09-16 11:00:10] [DEBUG] Analyzing token validation logic...
[2026-09-16 11:03:45] [INFO] ✓ Localization complete (223 seconds)
[2026-09-16 11:03:45] [INFO] Top candidate: src/auth/middleware.js (confidence: 0.88)

[2026-09-16 11:03:46] [INFO] Stage 2/4: Reproduction
[2026-09-16 11:03:47] [DEBUG] Creating Docker sandbox...
[2026-09-16 11:04:00] [DEBUG] Container ID: d8f3a2b1c4e5
[2026-09-16 11:04:01] [DEBUG] Installing npm dependencies...
[2026-09-16 11:05:30] [DEBUG] Running: npm test -- auth.test.js
[2026-09-16 11:06:15] [DEBUG] Test output: 3 failed, 12 passed
[2026-09-16 11:06:16] [INFO] ✓ Error reproduced successfully
[2026-09-16 11:06:16] [INFO] Root cause: Missing expiration check before token.exp access

[2026-09-16 11:06:17] [INFO] Stage 3/4: Patch Generation
[2026-09-16 11:06:18] [DEBUG] Building context for src/auth/middleware.js...
[2026-09-16 11:06:30] [DEBUG] Context size: 3,452 tokens
[2026-09-16 11:06:31] [DEBUG] Generating patches with beam_search=3...
[2026-09-16 11:09:45] [INFO] ✓ Generated 3 patch candidates

[2026-09-16 11:09:46] [INFO] Stage 4/4: Validation
[2026-09-16 11:09:47] [DEBUG] Testing patch #1...
[2026-09-16 11:10:30] [DEBUG] Patch #1: 3 tests failed (regression detected)
[2026-09-16 11:10:31] [DEBUG] Testing patch #2...
[2026-09-16 11:11:15] [INFO] ✓ Patch #2: All tests passed!
[2026-09-16 11:11:15] [INFO] Test results: 15 passed, 0 failed

[2026-09-16 11:11:16] [INFO] ✓ Success!
[2026-09-16 11:11:16] [INFO] Total time: 11 minutes 16 seconds
[2026-09-16 11:11:16] [INFO] Patch: .swe-agent/sessions/auth-fix-20260916-110000/final_patch.diff
```

### Generated Patch

```diff
--- a/src/auth/middleware.js
+++ b/src/auth/middleware.js
@@ -18,10 +18,17 @@ const jwt = require('jsonwebtoken');
 
 function validateToken(req, res, next) {
     const token = req.headers.authorization?.split(' ')[1];
+    
     if (!token) {
         return res.status(401).json({ error: 'No token provided' });
     }
     
-    const decoded = jwt.decode(token);
-    if (decoded.exp < Date.now() / 1000) {
+    try {
+        const decoded = jwt.verify(token, process.env.JWT_SECRET);
+        
+        if (!decoded.exp || decoded.exp < Date.now() / 1000) {
+            return res.status(401).json({ error: 'Token expired' });
+        }
+        
+        req.user = decoded;
+        next();
+    } catch (err) {
         return res.status(401).json({ error: 'Token expired' });
     }
-    req.user = decoded;
-    next();
 }
```

### Applying and Testing

```bash
# Apply the patch
git apply .swe-agent/sessions/auth-fix-20260916-110000/final_patch.diff

# Run tests to verify
npm test

# Test manually with expired token
curl -H "Authorization: Bearer <expired_token>" http://localhost:3000/api/protected
# Should return: {"error": "Token expired"}

# Commit
git add src/auth/middleware.js
git commit -m "fix: properly validate JWT token expiration

- Use jwt.verify instead of jwt.decode for signature validation
- Add null check for decoded.exp before comparison
- Properly catch and handle verification errors

Fixes #87"
```

---

## Example 3: Using Configuration Options

### Scenario

You want to customize SWE Agent's behavior for a large, complex codebase.

### Create Configuration File

```bash
# Create swe-agent.toml in your project root
cat > swe-agent.toml << 'EOF'
[swe_agent]
# Extended timeouts for large codebase
localization_timeout = 900       # 15 minutes
reproduction_timeout = 1200      # 20 minutes
patch_generation_timeout = 600   # 10 minutes
validation_timeout = 900         # 15 minutes
global_timeout = 3600            # 60 minutes total

# More aggressive retry strategy
localization_max_retries = 5
reproduction_max_retries = 7
patch_max_retries = 7           # Generate more patch candidates

# Increased resource limits
docker_cpu_limit = 4
docker_memory_limit = "8g"
docker_timeout = 900

# Larger output limits for detailed logs
max_tool_output_size = 20480    # 20KB
max_test_output_size = 10240    # 10KB
max_file_size = 100000          # 100K characters
max_search_results = 200

# Storage configuration
storage_base_path = ".swe-agent-custom"
max_session_size = 2147483648   # 2GB
max_sessions = 50

# Debug logging
log_level = "DEBUG"
log_format = "json"

# LLM configuration
llm_model = "claude-sonnet-4-20250514"
llm_max_tokens = 8192           # Double the default
llm_temperature = 0.1           # Slightly more creative
EOF
```

### Using Environment Variables Instead

```bash
# Create environment file
cat > .env.swe-agent << 'EOF'
# Timeouts
export SWE_AGENT_LOCALIZATION_TIMEOUT=900
export SWE_AGENT_REPRODUCTION_TIMEOUT=1200
export SWE_AGENT_PATCH_GENERATION_TIMEOUT=600
export SWE_AGENT_VALIDATION_TIMEOUT=900
export SWE_AGENT_GLOBAL_TIMEOUT=3600

# Retries
export SWE_AGENT_LOCALIZATION_MAX_RETRIES=5
export SWE_AGENT_REPRODUCTION_MAX_RETRIES=7
export SWE_AGENT_PATCH_MAX_RETRIES=7

# Docker resources
export SWE_AGENT_DOCKER_CPU_LIMIT=4
export SWE_AGENT_DOCKER_MEMORY_LIMIT="8g"
export SWE_AGENT_DOCKER_TIMEOUT=900

# Logging
export SWE_AGENT_LOG_LEVEL="DEBUG"
export SWE_AGENT_LOG_FORMAT="console"
EOF

# Load environment
source .env.swe-agent

# Run with loaded configuration
poetry run swe-agent --issue 123 --repo .
```

### Running with Configuration

```bash
# Option 1: Use config file
poetry run swe-agent \
  --config swe-agent.toml \
  --issue "https://github.com/org/large-repo/issues/456" \
  --repo /path/to/large-repo

# Option 2: Override specific settings via CLI
poetry run swe-agent \
  --config swe-agent.toml \
  --issue 456 \
  --repo . \
  --timeout 7200  # Override global timeout to 2 hours

# Option 3: Mix config file and environment variables
export SWE_AGENT_LOG_LEVEL="DEBUG"  # Override just logging
poetry run swe-agent --config swe-agent.toml --issue 456 --repo .
```

### Example Output with Custom Configuration

```
[2026-09-16 12:00:00] [DEBUG] Loading configuration from: swe-agent.toml
[2026-09-16 12:00:00] [DEBUG] Config loaded: global_timeout=3600s
[2026-09-16 12:00:01] [INFO] Session ID: large-fix-20260916-120000
[2026-09-16 12:00:02] [DEBUG] Docker resources: 4 CPUs, 8GB RAM

[2026-09-16 12:00:03] [INFO] Stage 1/4: Localization (timeout: 900s)
[2026-09-16 12:00:04] [DEBUG] max_search_results=200, max_retries=5
...
[2026-09-16 12:14:30] [INFO] ✓ Localization complete (867 seconds, 4 retries)

[2026-09-16 12:14:31] [INFO] Stage 2/4: Reproduction (timeout: 1200s)
...
```

---

## Example 4: Resuming a Session

### Scenario

Your SWE Agent session was interrupted (network issue, system restart, etc.) and you want to resume it.

### Initial Run (Interrupted)

```bash
poetry run swe-agent --issue 789 --repo .
```

```
[2026-09-16 13:00:00] Starting SWE Agent...
[2026-09-16 13:00:01] Session ID: resume-demo-20260916-130000
[2026-09-16 13:00:05] Stage 1/4: Localization
[2026-09-16 13:02:30] ✓ Localization complete
[2026-09-16 13:02:31] Stage 2/4: Reproduction
[2026-09-16 13:05:45] ✓ Reproduction complete
[2026-09-16 13:05:46] Stage 3/4: Patch Generation
[2026-09-16 13:07:15] Generating patches...
^C  # User interrupts with Ctrl+C
[2026-09-16 13:08:00] Interrupted! Session state saved.
[2026-09-16 13:08:00] Resume with: swe-agent --resume resume-demo-20260916-130000
```

### Finding the Session ID

```bash
# If you forgot the session ID, list recent sessions
ls -lt .swe-agent/sessions/ | head -5

# Output:
# drwxr-xr-x resume-demo-20260916-130000
# drwxr-xr-x other-session-20260916-120000
# ...

# Or search by date
ls .swe-agent/sessions/ | grep "20260916"

# View session details
cat .swe-agent/sessions/resume-demo-20260916-130000/state.json
```

### Resuming the Session

```bash
# Resume by session ID
poetry run swe-agent --resume resume-demo-20260916-130000
```

```
[2026-09-16 14:00:00] Resuming session: resume-demo-20260916-130000
[2026-09-16 14:00:01] Loading previous state...
[2026-09-16 14:00:02] Completed stages: Localization, Reproduction
[2026-09-16 14:00:02] Current stage: Patch Generation (interrupted at 35%)
[2026-09-16 14:00:03] Resuming Stage 3/4: Patch Generation
[2026-09-16 14:02:30] ✓ Patch generation complete
[2026-09-16 14:02:31] Stage 4/4: Validation
[2026-09-16 14:05:45] ✓ Validation complete
[2026-09-16 14:05:46] ✓ Success!
[2026-09-16 14:05:46] Patch: .swe-agent/sessions/resume-demo-20260916-130000/final_patch.diff
```

### Checking Session Status

```bash
# Check status of a running session (from another terminal)
poetry run swe-agent --status resume-demo-20260916-130000
```

```
Session: resume-demo-20260916-130000
Status: running
Started: 2026-09-16 14:00:00
Duration: 5 minutes 46 seconds

Stages:
  ✓ Localization     (completed in 150s)
  ✓ Reproduction     (completed in 194s)
  ✓ Patch Generation (completed in 145s)
  ⟳ Validation       (running, elapsed: 195s)

Current activity: Running test suite (pytest)
```

### Resuming After Failure

```bash
# If a session failed, you can resume with different configuration
poetry run swe-agent --resume failed-session-id

# Or resume with increased timeouts
export SWE_AGENT_VALIDATION_TIMEOUT=1200
poetry run swe-agent --resume failed-session-id
```

---

## Example 5: Debugging Failed Runs

### Scenario

SWE Agent failed to fix an issue, and you need to understand why.

### Failed Run Output

```bash
poetry run swe-agent --issue 999 --repo .
```

```
[2026-09-16 15:00:00] Starting SWE Agent...
[2026-09-16 15:00:01] Session ID: debug-demo-20260916-150000
[2026-09-16 15:00:05] Stage 1/4: Localization
[2026-09-16 15:02:30] ✓ Localization complete
[2026-09-16 15:02:31] Stage 2/4: Reproduction
[2026-09-16 15:05:45] ✗ Reproduction failed
[2026-09-16 15:05:46] Error: Could not reproduce the error
[2026-09-16 15:05:46] Session state saved to: .swe-agent/sessions/debug-demo-20260916-150000
```

### Step 1: Review Session Logs

```bash
# View execution log
cat .swe-agent/sessions/debug-demo-20260916-150000/execution.log

# Use jq for JSON logs
cat .swe-agent/sessions/debug-demo-20260916-150000/execution.log | jq 'select(.level=="ERROR")'

# Example output:
# {
#   "timestamp": "2026-09-16T15:05:45Z",
#   "level": "ERROR",
#   "event": "reproduction_failed",
#   "stage": "reproduction",
#   "message": "Test command exited with code 0 (expected non-zero)",
#   "details": {
#     "command": "pytest tests/test_feature.py",
#     "exit_code": 0,
#     "stdout": "... 15 passed ...",
#     "stderr": ""
#   }
# }
```

### Step 2: View Detailed State

```bash
# View full session state
cat .swe-agent/sessions/debug-demo-20260916-150000/state.json | jq .

# View specific stage results
cat .swe-agent/sessions/debug-demo-20260916-150000/state.json | jq '.stages.reproduction'

# Example output:
# {
#   "status": "failed",
#   "started_at": "2026-09-16T15:02:31Z",
#   "completed_at": "2026-09-16T15:05:45Z",
#   "duration": 194,
#   "result": null,
#   "error": {
#     "type": "agent_error",
#     "message": "Could not reproduce the error",
#     "details": {
#       "attempts": 5,
#       "last_exit_code": 0,
#       "expected": "non-zero exit code or test failure"
#     },
#     "recoverable": false,
#     "timestamp": "2026-09-16T15:05:45Z"
#   },
#   "retries": 5
# }
```

### Step 3: Inspect Tool Calls

```bash
# View all tool calls
cat .swe-agent/sessions/debug-demo-20260916-150000/tool_calls.json | jq .

# Filter by tool name
cat .swe-agent/sessions/debug-demo-20260916-150000/tool_calls.json | \
  jq '.[] | select(.tool_name=="run_test")'

# Example output shows the test command that was run:
# {
#   "id": "call-123",
#   "tool_name": "run_test",
#   "parameters": {
#     "command": "pytest tests/test_feature.py",
#     "timeout": 600
#   },
#   "timestamp": "2026-09-16T15:03:30Z",
#   "caller": "ReproductionAgent"
# }
```

### Step 4: Manual Reproduction

```bash
# Get the Docker container (if still running)
docker ps -a | grep debug-demo-20260916-150000

# Or create a new container with the same setup
docker run -it --rm \
  -v $(pwd):/workspace \
  -w /workspace \
  python:3.11 \
  /bin/bash

# Inside container, manually run the commands
cd /workspace
pip install -r requirements.txt
pytest tests/test_feature.py -v

# Check if the error actually occurs
# If tests pass, the issue might be:
# 1. Missing reproduction steps in the issue
# 2. Environment-specific bug
# 3. Test needs specific setup
```

### Step 5: Re-run with Debug Logging

```bash
# Enable debug logging for more details
export SWE_AGENT_LOG_LEVEL="DEBUG"
export SWE_AGENT_LOG_FORMAT="console"  # Human-readable

# Run again
poetry run swe-agent --issue 999 --repo . --verbose
```

### Step 6: Analyze Localization Results

```bash
# Check what files were found
cat .swe-agent/sessions/debug-demo-20260916-150000/localization_result.json | jq '.candidates'

# Example output:
# [
#   {
#     "file": "src/feature.py",
#     "confidence": 0.85,
#     "reason": "Found in stack trace"
#   },
#   {
#     "file": "src/utils.py",
#     "confidence": 0.42,
#     "reason": "Contains error keyword"
#   }
# ]

# If confidence is low, the issue description might need improvement
```

### Step 7: Common Failure Patterns and Solutions

#### Pattern 1: "Could not reproduce the error"

**Diagnosis:**
```bash
# Check test output
cat .swe-agent/sessions/*/reproduction_logs.txt
```

**Solutions:**
- Ensure issue includes actual error message or stack trace
- Add reproduction steps to issue description
- Check if tests require specific environment setup
- Verify test framework is correctly detected

#### Pattern 2: "Localization found no candidates"

**Diagnosis:**
```bash
# Check search results
cat .swe-agent/sessions/*/localization_logs.txt | grep "search_results"
```

**Solutions:**
- Add more specific error messages to issue
- Include file names or function names in issue
- Check if repository structure is unusual
- Try adding stack trace to issue

#### Pattern 3: "All patches failed validation"

**Diagnosis:**
```bash
# View generated patches
ls .swe-agent/sessions/*/patches/
cat .swe-agent/sessions/*/patches/patch_*.diff

# Check validation errors
cat .swe-agent/sessions/*/validation_logs.txt
```

**Solutions:**
- Patches may be too complex (>50 lines)
- Tests may have flaky behavior
- Issue may require architectural changes
- Increase `patch_max_retries` for more candidates

### Step 8: Report Issues

If SWE Agent consistently fails, report with:

```bash
# Create debug bundle
tar -czf swe-agent-debug.tar.gz \
  .swe-agent/sessions/debug-demo-20260916-150000/ \
  swe-agent.toml \
  pyproject.toml

# Upload to GitHub issue with:
# - Session ID
# - Issue URL
# - Repository structure
# - Debug bundle
```

---

## Additional Examples

### Running on a Java Project

```bash
cd my-java-project

# SWE Agent auto-detects Maven/Gradle
poetry run swe-agent --issue 101 --repo .

# Explicit test command (if needed)
export SWE_AGENT_TEST_COMMAND="mvn test"
poetry run swe-agent --issue 101 --repo .
```

### Running on a Rust Project

```bash
cd my-rust-project

# SWE Agent auto-detects Cargo
poetry run swe-agent --issue 202 --repo .

# Specific test
export SWE_AGENT_TEST_COMMAND="cargo test test_name"
poetry run swe-agent --issue 202 --repo .
```

### Batch Processing Multiple Issues

```bash
# Create a script
cat > fix_issues.sh << 'EOF'
#!/bin/bash
for issue in 100 101 102 103; do
  echo "Fixing issue #$issue..."
  poetry run swe-agent --issue $issue --repo . --quiet
  sleep 60  # Rate limiting
done
EOF

chmod +x fix_issues.sh
./fix_issues.sh
```

### Integration with CI/CD

```yaml
# .github/workflows/auto-fix.yml
name: Auto Fix Issues

on:
  issues:
    types: [labeled]

jobs:
  auto-fix:
    if: github.event.label.name == 'auto-fix'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install SWE Agent
        run: |
          pip install poetry
          git clone https://github.com/username/swe-agent.git
          cd swe-agent && poetry install
      
      - name: Run SWE Agent
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          cd swe-agent
          poetry run swe-agent \
            --issue ${{ github.event.issue.number }} \
            --repo ${{ github.workspace }}
      
      - name: Create Pull Request
        if: success()
        uses: peter-evans/create-pull-request@v5
        with:
          title: "Fix #${{ github.event.issue.number }}"
          body: |
            Auto-generated fix for #${{ github.event.issue.number }}
            
            Generated by SWE Agent
          branch: auto-fix-${{ github.event.issue.number }}
```

---

## Next Steps

- Return to [USER_GUIDE.md](./USER_GUIDE.md) for detailed configuration options
- See [SYSTEM_DESIGN.md](../SYSTEM_DESIGN.md) for architecture details
- Explore the source code for advanced customization

---

**Questions or Issues?**

Open an issue on GitHub: https://github.com/yourusername/swe-agent/issues