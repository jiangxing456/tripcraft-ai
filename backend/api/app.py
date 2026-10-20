"""FastAPI 装配：真实模式用 PostgreSQL 检查点，--demo 使用内存检查点。"""

import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from redis.asyncio import Redis

from router.plan import router as plan_router
from router.planner import router as planner_router
from services.db_service import initialize_db_pool, close_db_pool
from services.planner import Planner
from services.checkpoints import PostgresCheckpoints


@asynccontextmanager
async def lifespan(app):
    demo = os.getenv("TRIPCRAFT_DEMO") == "1"
    async with AsyncExitStack() as stack:
        if demo:
            saver = InMemorySaver()
            backend = "memory（演示重启后清空）"
        else:
            await initialize_db_pool()
            stack.push_async_callback(close_db_pool)
            dsn = os.environ["DATABASE_URL"].replace(
                "postgresql+asyncpg://", "postgresql://"
            )
            saver = stack.enter_context(PostgresCheckpoints.from_conn_string(dsn))
            await asyncio.to_thread(saver.setup)
            backend = "PostgreSQL"
        cache = Redis.from_url(
            os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        stack.push_async_callback(cache.aclose)
        try:
            available = await cache.ping()
        except Exception:
            available = False
        app.state.planner = Planner(saver, cache if available else None, demo)
        app.state.checkpoint_backend = backend
        app.state.redis_available = bool(available)
        try:
            yield
        finally:
            tasks = list(app.state.planner.tasks.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="TripCraft LangGraph API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(plan_router)
app.include_router(planner_router)


@app.get("/api/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
