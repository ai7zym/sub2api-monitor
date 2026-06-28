"""数据库引擎与会话管理。支持延迟初始化，setup 完成前不连接数据库。"""
import logging

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from . import config

logger = logging.getLogger("price_monitor.db")

engine = None


def _connect_args(db_url: str) -> dict:
    if "sqlite" in db_url:
        return {"check_same_thread": False}
    return {}


def create_db_engine(db_url: str):
    global engine
    engine = create_engine(db_url, echo=False, connect_args=_connect_args(db_url))


def test_db_connection(db_url: str) -> str | None:
    """测试数据库连接，成功返回 None，失败返回错误信息。"""
    try:
        test_engine = create_engine(db_url, echo=False, connect_args=_connect_args(db_url))
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        test_engine.dispose()
        return None
    except ImportError as e:
        return f"缺少数据库驱动: {e}。请 pip install psycopg2-binary"
    except Exception as e:
        return str(e)


def init_db(db_url: str | None = None) -> None:
    """初始化数据库引擎并创建所有表（若不存在），运行增量迁移。"""
    global engine
    url = db_url or config.get_database_url()
    engine = create_engine(url, echo=False, connect_args=_connect_args(url))

    from . import models  # noqa: F401
    SQLModel.metadata.create_all(engine)

    # 增量迁移（SQLite 专用）
    if "sqlite" in url:
        _migrate_sqlite()
    logger.info("数据库初始化完成: %s", url.split("@")[-1] if "@" in url else url)


def _migrate_sqlite() -> None:
    with engine.begin() as conn:
        for table, col, coltype in [
            ("site", "token", "TEXT"),
            ("pricesnapshot", "key_id", "INTEGER"),
        ]:
            cols = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            col_names = [c[1] for c in cols]
            if col not in col_names:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))


def get_engine():
    if engine is None:
        raise RuntimeError("数据库未初始化")
    return engine


def get_session():
    """FastAPI 依赖：提供数据库会话。"""
    if engine is None:
        raise RuntimeError("数据库未初始化")
    with Session(engine) as session:
        yield session
