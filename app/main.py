"""FastAPI 应用入口。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from . import config
from .auth import require_auth
from .routers import auth, monitor, pages, setup, sites

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("price_monitor")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        result = await require_auth(request)
        if hasattr(result, "status_code") and result.status_code in (301, 302):
            return result
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.is_initialized():
        from .database import init_db
        from .scheduler import shutdown_scheduler, start_scheduler
        init_db()
        start_scheduler()
    else:
        logger.info("未初始化，访问 /setup 进行设置")
    yield
    if config.is_initialized():
        from .scheduler import shutdown_scheduler
        shutdown_scheduler()


app = FastAPI(title="上游价格监控", version="2.0.0", lifespan=lifespan)

# 中间件
app.add_middleware(AuthMiddleware)

# 路由
app.include_router(auth.router)
app.include_router(setup.router)
app.include_router(pages.router)
app.include_router(sites.router)
app.include_router(monitor.router)
