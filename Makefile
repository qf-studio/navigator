# Navigator Plugin - Quality Gate Targets
# These targets support the CI/CD quality gates

.PHONY: build test lint clean conformance-check mod-validate mod-test mod-typecheck test-all

# Build target - for a plugin, validate JSON and check Python syntax
build:
	@echo "Validating plugin configuration..."
	@python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))" && echo "plugin.json: OK"
	@python3 -c "import json; json.load(open('.claude-plugin/marketplace.json'))" && echo "marketplace.json: OK"
	@echo "Checking Python syntax..."
	@python3 -m py_compile skills/nav-loop/functions/status_generator.py && echo "status_generator.py: OK"
	@echo "Build validation complete."

# Directories with genuine unittest suites. Each test_*.py imports its sibling
# module by bare name, so discovery must run per-directory (from inside each dir).
# (The two former non-test files that matched test_*.py — frontend-component's
# test_generator.py and product-design's test_mcp_connection.py — were renamed to
# file_generator.py / check_mcp_connection.py in TASK-45, so they no longer poison
# discovery.)
TEST_DIRS := \
	hooks \
	hooks/nav_hook_lib \
	tests/golden \
	tests/harness-conformance \
	skills/nav-upgrade/functions \
	skills/nav-sync-claude/functions \
	skills/nav-simplify/scripts \
	skills/nav-workflow/functions \
	skills/nav-init/functions \
	skills/nav-loop/functions \
	skills/nav-release/functions \
	skills/nav-start/functions \
	skills/nav-graph/functions \
	skills/nav-brief/functions \
	skills/nav-triz/functions \
	skills/nav-deep-research/functions \
	skills/nav-onboard/functions \
	skills/nav-profile/functions \
	skills/nav-features/functions \
	skills/nav-task/functions \
	scripts

# Standalone shell test scripts (each exits non-zero on failure).
SHELL_TESTS := \
	tests/test-check-version.sh

# Test target - run all Python unit tests (per-directory discovery) + shell tests
test:
	@echo "Running unit tests..."
	@fail=0; \
	for d in $(TEST_DIRS); do \
		if ls $$d/test_*.py >/dev/null 2>&1; then \
			echo "--- $$d ---"; \
			( cd $$d && python3 -m unittest discover -p "test_*.py" ) || fail=1; \
		fi; \
	done; \
	for t in $(SHELL_TESTS); do \
		echo "--- $$t ---"; \
		bash $$t || fail=1; \
	done; \
	if [ $$fail -ne 0 ]; then echo "TESTS FAILED"; exit 1; fi; \
	echo "All unit tests passed."


# Claude Code mod (v8 runtime, TASK-84): hooks/hooks.json -> hooks/mod/register.tsx.
# Needs the claude CLI >= 2.1.287; both targets run offline without credentials.
mod-validate:
	@claude plugin validate .claude-plugin/plugin.json

mod-test:
	@claude plugin test .

# Type-check against the engine-written types in .claude-plugin/types/ (laid the first
# time a 2.1.287+ session loads the plugin, e.g. `claude -p --plugin-dir . ok`).
mod-typecheck:
	@test -f .claude-plugin/types/tsconfig.json || { echo "mod-typecheck: load the plugin once with claude >= 2.1.287 to lay .claude-plugin/types/"; exit 1; }
	@npx --no-install tsc -p . --noEmit

test-all: test mod-validate mod-test

# Conformance gate (TASK-58) — a results file must exist for the installed
# Claude Code version. Probes are live-driven and cannot run in CI; when this
# fails, re-drive the suite per tests/harness-conformance/run.md.
conformance-check:
	@v=$$(claude --version | awk '{print $$1}'); \
	f="tests/harness-conformance/results/cc-$$v.json"; \
	if [ -f "$$f" ]; then \
		echo "conformance-check: OK ($$f)"; \
	else \
		echo "conformance-check: MISSING conformance results for Claude Code $$v"; \
		echo "expected file: $$f"; \
		echo "re-drive the suite: tests/harness-conformance/run.md"; \
		exit 1; \
	fi

# Lint target - check code style
lint:
	@echo "Running lint checks..."
	@python3 -m py_compile skills/nav-loop/functions/status_generator.py && echo "Python syntax: OK"
	@echo "Lint complete."

# Clean target - remove generated files
clean:
	@echo "Cleaning..."
	@rm -rf coverage/
	@rm -rf __pycache__/
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean complete."
