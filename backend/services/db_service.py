"""共用 PostgreSQL 连接池；初始化失败时不保留半初始化状态。"""

import os
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_engine = None
_session_factory = None


async def initialize_db_pool():
    global _engine, _session_factory
    if _engine is not None:
        return
    url = os.environ["DATABASE_URL"].replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
    engine = create_async_engine(
        url, pool_pre_ping=True, connect_args={"server_settings": {"timezone": "UTC"}}
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        await engine.dispose()
        raise
    _engine = engine
    _session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def close_db_pool():
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = _session_factory = None


@asynccontextmanager
async def get_db_session():
    if _session_factory is None:
        await initialize_db_pool()
    async with _session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
