"""FastAPI 应用入口：装配 lifespan、CORS 中间件和各路路由。

lifespan：https://fastapi.tiangolo.com/advanced/events/
CORS：    https://fastapi.tiangolo.com/tutorial/cors/
路由拆分：https://fastapi.tiangolo.com/tutorial/bigger-applications/
"""

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware  # starlette/middleware/cors.py:15
from loguru import logger  # 全局单例，import 即用；统一配置见 config/logger.py
from datetime import datetime, timezone
from contextlib import asynccontextmanager  # https://docs.python.org/3/library/contextlib.html#contextlib.asynccontextmanager
from services.db_service import initialize_db_pool, close_db_pool  # db_service.py:42、:88
from router.plan import router as plan_router  # 前缀 /api/plan 定义在 router/plan.py:16

router = APIRouter(prefix="/api")  # prefix 在注册路由时拼接：fastapi/routing.py:934


@router.get("/health", summary="API Health Check")  # summary 只进 Swagger 文档：https://fastapi.tiangolo.com/tutorial/path-operation-configuration/
async def health_check():
    logger.debug("Health check requested")
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}  # 带时区的 UTC，官方不推荐 utcnow()：https://docs.python.org/3/library/datetime.html#datetime.datetime.now


@asynccontextmanager
async def lifespan(app: FastAPI):  # 启动/关闭只跑一次，由 Starlette 在 ASGI lifespan 消息里调用：starlette/routing.py:683
    # 启动逻辑
    logger.info("API server started")

    # 初始化数据库连接池
    logger.info("Initializing database connection pool")
    await initialize_db_pool()  # 幂等建池：services/db_service.py:42
    logger.info("Database connection pool initialized")

    yield  # 分界线：yield 之上是启动逻辑，之下是关闭逻辑

    # 关闭逻辑：释放数据库连接池
    logger.info("Closing database connection pool")
    await close_db_pool()  # 释放连接池：services/db_service.py:88

    logger.info("API server shutting down")


app = FastAPI(
    title="TripCraft AI API",  # title/description/version 只影响 /docs 与 /openapi.json
    description="API for running intelligent trip planning in the background",
    version="0.1.0",
    lifespan=lifespan,  # 转交给内部 APIRouter：fastapi/applications.py:938；旧的 on_event 已废弃：同文件 :4470
)

app.add_middleware(  # 必须在应用启动前调用，否则 RuntimeError：starlette/applications.py:123
    CORSMiddleware,
    allow_origins=["*"],  # 配 allow_credentials 时会回显具体 Origin 而非 "*"：starlette/middleware/cors.py:36、:159
    allow_credentials=True,
    allow_methods=["*"],  # "*" 展开成 ALL_METHODS：starlette/middleware/cors.py:27
    allow_headers=["*"],
)


app.include_router(router)  # 启动前静态装配路由表：fastapi/applications.py:1255
app.include_router(plan_router)  # /api/plan/*
