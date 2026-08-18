import pytest

from app.agent import _PENDING, _SESSIONS


@pytest.fixture(autouse=True)
def _clean_agent_state():
    """Agent sessions/pending confirmations live in module-level dicts —
    clear them before and after every test so one test can't leak state
    (a stale confirmation_id, a stuck session) into the next."""
    _PENDING.clear()
    _SESSIONS.clear()
    yield
    _PENDING.clear()
    _SESSIONS.clear()
