"""认证 API：登录、登出。"""
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session, select

from .. import auth
from ..database import get_engine
from ..models import User

router = APIRouter(tags=["auth"])


@router.get("/login")
def login_page(request: Request):
    from .. import config as app_config
    from ..routers.pages import templates
    if app_config.is_initialized():
        # 已登录则跳首页
        token = request.cookies.get("token")
        if token and auth.decode_token(token):
            return RedirectResponse("/", 302)
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    eng = get_engine()
    with Session(eng) as session:
        user = session.exec(
            select(User).where(User.email == email.strip().lower())
        ).first()
    if not user or not auth.verify_password(password, user.password_hash):
        raise HTTPException(401, "邮箱或密码错误")

    token = auth.create_access_token(user.id)
    resp = RedirectResponse("/", 302)
    resp.set_cookie(
        key="token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=86400 * 7,
        path="/",
    )
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", 302)
    resp.delete_cookie("token", path="/")
    return resp
