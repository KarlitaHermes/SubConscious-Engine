# SubConscious Engine — Coding Standards

## General Principles
- **Simplicity over complexity** — Every function should do one thing
- **Explicit over implicit** — No magic, no hidden state
- **Fail gracefully** — Log errors, don't crash
- **Minimal dependencies** — Only aiohttp and pyyaml

## File Organization
- Each module in its own file
- No file longer than 200 lines
- Clear separation: config, logic, delivery, state

## Naming Conventions
- `snake_case` for functions and variables
- `PascalCase` for classes
- `UPPER_CASE` for constants
- Descriptive names: `is_session_idle()` not `check()`

## Function Signatures
- Type hints on ALL functions
- Docstrings on ALL public functions
- Return type annotations required

Example:
```python
async def is_session_idle(
    state: StateManager,
    session_id: str,
    idle_threshold_minutes: int,
) -> bool:
    """Check if a session has been idle longer than the threshold.

    Args:
        state: State manager instance.
        session_id: The session to check.
        idle_threshold_minutes: Minutes of inactivity before considered idle.

    Returns:
        True if the session is idle, False otherwise.
    """
```

## Error Handling
- Catch specific exceptions, not bare `except`
- Log with context: `logger.error("Failed to inject: %s", exc, exc_info=True)`
- Never swallow errors silently
- Use custom exception classes for domain errors

## Logging
- Use module-level logger: `logger = logging.getLogger(__name__)`
- INFO for normal operations
- WARNING for recoverable issues
- ERROR for failures
- DEBUG for verbose diagnostics
- Never log secrets/tokens

## Testing
- Every module has a corresponding test file
- Tests use pytest with asyncio support
- Mock external HTTP calls (no real network in tests)
- Test file naming: `test_<module_name>.py`

## Git Commits
- One logical change per commit
- Commit messages: `type: description` (feat, fix, refactor, docs)
- No commits with "WIP" or "fix fix fix"
