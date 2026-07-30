# SubConscious Engine — Coding Standards

## General principles

- **Simplicity over complexity** — Every function should do one thing
- **Explicit over implicit** — No magic, no hidden state
- **Fail gracefully** — Log errors, don't crash the loop
- **Minimal dependencies** — Runtime: aiohttp and pyyaml only

## File organization

- One concern per module; package by role: `config/`, `events/`, `sources/`, `router/`, `delivery/`, `checks/`
- Prefer small files; split when a module grows past ~250 lines unless state/cohesion argues otherwise
- `app.py` orchestrates only — no routing or source logic there

## Naming conventions

- `snake_case` for functions and variables
- `PascalCase` for classes
- `UPPER_CASE` for constants
- Descriptive names: `is_session_idle()` not `check()`

## Function signatures

- Type hints on all functions
- Docstrings on all public functions
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

## Error handling

- Catch specific exceptions, not bare `except`
- Log with context: `logger.error("Failed to inject: %s", exc, exc_info=True)`
- Never swallow errors silently
- Source/consume loops: log and continue; config load: fail fast

## Logging

- Module-level logger: `logger = logging.getLogger(__name__)`
- INFO for normal operations; WARNING recoverable; ERROR failures; DEBUG diagnostics
- Never log secrets/tokens

## Testing

- Corresponding `tests/test_<area>.py` for non-trivial modules
- pytest + pytest-asyncio (`asyncio_mode = auto`)
- Mock external HTTP — no real network or live Telegram injects in unit tests
- Integration against live sessions only with a dedicated test config/session (see `TODO.md`)

## Public / committed content

Sanitize anything that might land on GitHub (see `.cursor/rules/sanitize-public-content.mdc`): no live config/state, real session IDs, personal paths, or production cron UUIDs.

## Git commits

- One logical change per commit
- Messages: `type: description` (feat, fix, refactor, docs, test)
- No “WIP” or “fix fix fix” commits
