"""初始化设置 API：测试数据库连接、完成安装。"""
from fastapi import APIRouter
from pydantic import BaseModel

from .. import auth, config
from ..database import init_db, test_db_connection
from ..models import SiteCreate, User
from ..crud import create_site as crud_create_site
from sqlmodel import Session, select

router = APIRouter(prefix="/api/setup", tags=["setup"])


class TestDbRequest(BaseModel):
    database_url: str


class SetupCompleteRequest(BaseModel):
    database_url: str
    email: str
    password: str
    sites: list[SiteCreate] = []


@router.post("/test-db")
def test_db(data: TestDbRequest):
    """测试数据库连接。"""
    err = test_db_connection(data.database_url)
    if err:
        return {"ok": False, "error": err}
    return {"ok": True}


@router.post("/complete")
def setup_complete(data: SetupCompleteRequest):
    """完成初始化设置。
    1. 用给定连接串初始化数据库（建表）
    2. 创建管理员用户
    3. 可选地创建初始站点
    4. 写 config.json 标记完成
    """
    # 确保 jwt_secret 已生成
    jwt_secret = config.get_jwt_secret()

    # 初始化数据库
    init_db(data.database_url)
    # 重新加载 engine
    from .. import database
    eng = database.get_engine()

    # 创建管理员
    with Session(eng) as session:
        # 检查是否已有用户（防止重复初始化）
        existing = session.exec(select(User).limit(1)).first()
        if not existing:
            user = User(
                email=data.email.strip().lower(),
                password_hash=auth.hash_password(data.password),
            )
            session.add(user)
            session.commit()

        # 创建初始站点
        for s in data.sites:
            crud_create_site(session, s)

    # 持久化配置
    config.save_config({
        "initialized": True,
        "database_url": data.database_url,
        "jwt_secret": jwt_secret,
    })

    return {"ok": True}
