"""日志配置。

把 loguru 作为项目统一的日志出口，并把标准库 logging 也接管过来，
这样 uvicorn / fastapi / agno 等第三方库的日志会走同一套格式。
"""

import inspect
import logging
import sys
from typing import Any, Callable, Dict

from loguru import logger

DEFAULT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def configure_logger(console_level: str = "INFO", log_format: str | None = None) -> None:
    """配置 loguru 的控制台输出（当前只输出到控制台，没有写文件）。"""
    # 先移除 loguru 的默认 handler，否则日志会重复打印
    logger.remove()

    logger.add(
        sys.stderr,
        format=log_format or DEFAULT_FORMAT,
        level=console_level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )


class InterceptHandler(logging.Handler):
    """把标准库 logging 的记录转发给 loguru，保证输出格式统一。"""

    def emit(self, record: logging.LogRecord) -> None:
        # 取对应的 loguru 级别；取不到就直接用数字级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 向上找到真正的调用方，让日志里的文件名/行号指向业务代码而不是这里
        frame, depth = inspect.currentframe(), 0
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def patch_std_logging() -> None:
    """接管标准库 logging 的日志（含 uvicorn / fastapi）。"""
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    for name in logging.root.manager.loggerDict.keys():
        std_logger = logging.getLogger(name)
        std_logger.handlers = [InterceptHandler()]
        std_logger.propagate = False

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logging.getLogger(logger_name).handlers = [InterceptHandler()]


def setup_logging(console_level: str = "INFO", intercept_stdlib: bool = True) -> None:
    """应用启动时调用一次：配置 loguru，并按需接管标准库 logging。"""
    configure_logger(console_level=console_level)
    if intercept_stdlib:
        patch_std_logging()
    logger.info("Logging configured successfully")


def logger_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]):
    """Hook：包一层工具函数调用，在调用前后各打一条日志。"""
    logger.info(f"About to call {function_name} with arguments: {arguments}")
    result = function_call(**arguments)
    logger.info(f"Function call completed with result: {result}")
    return result
