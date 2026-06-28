"""认证：JWT 签发、验证、中间件依赖。"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlmodel import Session, select

from . import config as app_config
from .database import get_engine, get_session
from .models import User

logger = logging.getLogger("price_monitor.auth")

ACCESS_TOKEN_EXPIRE_HOURS = 168  # 7 天


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]  # bcrypt 72 字节限制
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, app_config.get_jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> Optional[int]:
    """解析 token，返回 user_id 或 None。"""
    try:
        payload = jwt.decode(token, app_config.get_jwt_secret(), algorithms=["HS256"])
        return int(payload.get("sub", 0)) or None
    except (JWTError, ValueError):
        return None


def get_current_user_from_token(token: str) -> Optional[User]:
    user_id = decode_token(token)
    if not user_id:
        return None
    eng = get_engine()
    with Session(eng) as session:
        return session.get(User, user_id)


def get_token_from_request(request: Request) -> Optional[str]:
    """从 Cookie 中提取 token。"""
    return request.cookies.get("token")


# ----------------------------- FastAPI 依赖 -----------------------------
async def require_auth(request: Request):
    """中间件使用的 auth check：未登录则重定向 /login。"""
    if not app_config.is_initialized():
        # setup 模式下，非 setup 路径直接重定向到 /setup
        path = request.url.path
        if path == "/" or (
            not path.startswith("/setup")
            and not path.startswith("/api/setup")
            and not path.startswith("/docs")
            and not path.startswith("/openapi")
        ):
            return RedirectResponse("/setup", status_code=302)
        return True
    # 白名单路径
    path = request.url.path
    if path in ("/login", "/setup") or path.startswith("/api/setup") or path.startswith("/docs") or path.startswith("/openapi"):
        return True
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse("/login", status_code=302)
    user_id = decode_token(token)
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    return True


async def get_current_user(
    token: str = Cookie(None),
    session: Session = Depends(get_session),
) -> User:
    """依赖注入：获取当前登录用户。未认证抛出 401。"""
    if not token:
        raise HTTPException(401, "未登录")
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(401, "登录已过期")
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(401, "用户不存在")
    return user
