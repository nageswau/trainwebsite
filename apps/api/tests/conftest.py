import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _disable_schema_autocreate(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auto_create_schema", False)


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_pool_per_test():
    # pytest-asyncio (strict mode) gives each test its own event loop; the shared,
    # module-level `engine` in app.core.database pools asyncpg connections bound to
    # whichever loop opened them. Disposing before every test -- project-wide, not just
    # one file -- forces each test to open fresh connections on its own loop, rather
    # than intermittently reusing one attached to a previous test's now-closed loop
    # (surfaces as "Task ... got Future ... attached to a different loop").
    from app.core.database import engine

    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def db_session():
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
def enqueued(monkeypatch):
    """ENH-014: no Redis in tests. Every delivery published after a commit is captured here as (delivery_id, countdown);
    `tests.enh014_helpers.drain` sends them in-process."""
    from app.notifications import dispatch

    captured: list[tuple[str, int]] = []
    monkeypatch.setattr(dispatch, "_publish", lambda delivery_id, countdown: captured.append((delivery_id, countdown)))
    return captured


@pytest.fixture(autouse=True)
def _reset_broker_backoff(monkeypatch):
    """ENH-014 QAF-01: a test that makes a publish fail opens the broker back-off; start every test with it closed."""
    from app.notifications import dispatch

    monkeypatch.setattr(dispatch, "_broker_unavailable_until", 0.0, raising=False)
