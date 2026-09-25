"""
数据库服务模块 —— 用 SQLAlchemy 异步版连 PostgreSQL。

职责：维护全局的连接池 + 会话工厂，并对外提供两种拿会话的方式：
    1. get_db_session()  —— 上下文管理器，事务型操作走这个
    2. execute_query()   —— 直接跑一条原生 SQL 的便捷函数

参考出处（对应本机安装的 SQLAlchemy 2.0.41，路径相对 backend/）：
    - 异步 ORM 总览：https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
    - 连接池说明：  https://docs.sqlalchemy.org/en/20/core/pooling.html
    - 本机源码：.venv/Lib/site-packages/sqlalchemy/ext/asyncio/engine.py、
                .venv/Lib/site-packages/sqlalchemy/ext/asyncio/session.py
"""

import os
from typing import Any, AsyncGenerator, Dict, Optional
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine
)
from loguru import logger

# 数据库连接串，从环境变量读取。
# 注意：这里是在「模块导入时」就执行的，所以调用方必须先把 .env 加载好
# （main.py:6 的 load_dotenv() 就干这事，它排在 from api.app import app 之前）。
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgresql://"):
    # SQLAlchemy 的异步引擎必须挂在「异步驱动」上，所以要显式点名 asyncpg。
    # 而 .env 里写的（以及 psycopg 风格的）是同步前缀，这里做个替换。
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")#异步引擎需要异步驱动-create_async_engine这是一个异步引擎

# 全局单例：整个进程共用一份引擎和会话工厂。
# 这两个变量由下方 initialize_db_pool() 赋值，close_db_pool() 负责回收。
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

async def initialize_db_pool(pool_size: int = 10, max_overflow: int = 20) -> None:
    """初始化 SQLAlchemy 引擎和会话工厂（幂等：已初始化过就直接返回）。

    Args:
        pool_size: 连接池常驻的连接数上限
        max_overflow: 常驻连接用满后，允许临时超发的连接数
    """
    global _engine, _session_factory
    # 幂等保护：重复调用不会重建引擎（否则会泄漏一个连接池）
    if _engine is not None:
        return

    logger.info("Initializing SQLAlchemy engine and session factory")

    try:
        # create_async_engine 定义在 ext/asyncio/engine.py:70，参数基本透传给同步版 create_engine。
        # pool_size / max_overflow 的库默认值分别是 5 和 10（engine/create.py:441、:382），
        # 这里调大到 10 / 20，是为了扛住「6 个 Agent 串行跑、中间频繁读写状态」的并发量。
        _engine = create_async_engine(
            DATABASE_URL,
            echo=False,  # 改成 True 会把每条 SQL 打到日志里，调试用
            pool_size=pool_size,
            max_overflow=max_overflow,
            # 借出连接前先 ping 一下，自动剔除已断开的死连接
            # （PostgreSQL 空闲超时断开后，不 ping 会直接报错）
            pool_pre_ping=True,
        )

        # 会话工厂。两个参数都覆盖了库默认值（ext/asyncio/session.py:1701 处的默认是 True）：
        #   expire_on_commit=False —— commit 后对象属性不过期，取完数据还能接着读，不用再查一次库
        #   autoflush=False        —— 不自动把挂起的改动刷进库，避免查询时意外触发写操作
        _session_factory = async_sessionmaker(
            _engine,
            expire_on_commit=False,
            autoflush=False,
        )

        # 探活：真连一次库，确保上面那句没配错（连不上就在初始化阶段就报出来）
        async with _session_factory() as session:
            await session.execute(text("SELECT 1"))

        logger.info("SQLAlchemy engine and session factory initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize SQLAlchemy engine and session factory: {e}")
        raise

async def close_db_pool() -> None:
    """关闭引擎并释放连接池（一般只在服务停机时调用）。"""
    global _engine
    if _engine is not None:
        logger.info("Closing SQLAlchemy engine and connection pool")
        # dispose() 定义在 ext/asyncio/engine.py:1125：
        # 关闭所有「已归还」的连接；还借在外面的连接不会被强杀，
        # 而是等它们自己归还后再回收。
        await _engine.dispose()
        _engine = None

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取一个数据库会话（上下文管理器）。

    Returns:
        AsyncSession: SQLAlchemy 异步会话

    Example:
        ```python
        async with get_db_session() as session:
            result = await session.execute(text("SELECT * FROM users"))
            users = result.fetchall()
        ```
    """
    # 兜底初始化：允许调用方不做显式初始化，第一次用到时自动建池
    if _session_factory is None:
        await initialize_db_pool()

    # async with 退出时，AsyncSession 会自动 close()（把连接还给池子）
    async with _session_factory() as session:
        try:
            yield session#后面被调用方调用干活
        except Exception as e:
            # 业务代码抛异常时回滚，防止把「写了一半的事务」留在连接上
            await session.rollback()
            logger.error(f"Database session operation failed: {e}")
            raise

async def execute_query(query: str, params: Optional[Dict[str, Any]] = None) -> list:
    """执行一条 SQL 并返回结果行。

    Args:
        query: 要执行的原始 SQL
        params: 查询参数，配合 :name 占位符使用（防注入，别用字符串拼接）

    Returns:
        list: 查询结果

    Example:
        ```python
        results = await execute_query(
            "SELECT * FROM users WHERE email = :email",
            {"email": "user@example.com"}
        )
        ```
    """
    async with get_db_session() as session:
        try:
            # text() 把字符串包成 SQLAlchemy 的 TextClause
            # （sqlalchemy/sql/_elements_constructors.py:1604），params 会被安全地绑定成参数
            result = await session.execute(text(query), params or {})
            try:
                return result.fetchall()
            except Exception:
                # 走到这里说明这条语句根本不返回行（INSERT/UPDATE/DDL 等），
                # SQLAlchemy 会抛 ResourceClosedError，这里当成「无结果」处理
                return []
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            raise
