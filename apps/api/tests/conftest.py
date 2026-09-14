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
