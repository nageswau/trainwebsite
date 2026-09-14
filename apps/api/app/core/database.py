import json
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _json_default(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    json_serializer=lambda value: json.dumps(value, default=_json_default),
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session
