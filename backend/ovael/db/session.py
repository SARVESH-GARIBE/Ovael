"""Async engines. Writes go to the primary; dashboard reads can go to a read replica.

When `OVAEL_DATABASE_READ_URL` is unset, reads use the primary. Read-after-write paths (e.g. the
scan status a client polls right after submitting) always read from the primary.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..config import Settings
from .models import Base


def _engine(url: str, settings: Settings) -> AsyncEngine:
    if url.startswith("sqlite"):
        engine = create_async_engine(url, connect_args={"timeout": 30})

        @event.listens_for(engine.sync_engine, "connect")
        def _pragmas(conn, _):  # WAL lets readers run while the detector writes
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        return engine
    return create_async_engine(url, pool_size=settings.db_pool_size, max_overflow=settings.db_pool_size,
                               pool_pre_ping=True, pool_recycle=1800)


class Database:
    def __init__(self, settings: Settings):
        self.engine = _engine(settings.database_url, settings)
        self.read_engine = (_engine(settings.database_read_url, settings)
                            if settings.database_read_url else self.engine)
        self.session = async_sessionmaker(self.engine, expire_on_commit=False)
        self.read_session = async_sessionmaker(self.read_engine, expire_on_commit=False)

    async def create_schema(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def ping(self) -> bool:
        from sqlalchemy import text

        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    async def close(self) -> None:
        await self.engine.dispose()
        if self.read_engine is not self.engine:
            await self.read_engine.dispose()


__all__ = ["AsyncSession", "Database"]
