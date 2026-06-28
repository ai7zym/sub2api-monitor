"""数据模型：Site / PriceSnapshot / Alert / User，以及 API 请求/响应 schema。"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Field, SQLModel

_SHANGHAI_TZ = timezone(timedelta(hours=8))


def _now() -> datetime:
    return datetime.now(_SHANGHAI_TZ)


# ----------------------------- 数据库表 -----------------------------
class User(SQLModel, table=True):
    """管理员用户。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    created_at: datetime = Field(default_factory=_now)


class Site(SQLModel, table=True):
    """站点配置。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    domain: str = Field(index=True)
    email: str
    password: str
    remark: Optional[str] = None
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_now)
    token: Optional[str] = None


class PriceSnapshot(SQLModel, table=True):
    """每次抓取的历史快照。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(index=True, foreign_key="site.id")
    domain: str = Field(index=True)
    fetched_at: datetime = Field(default_factory=_now, index=True)
    balance: Optional[float] = None
    group_name: Optional[str] = None
    rate_multiplier: Optional[float] = None
    key_name: Optional[str] = None
    key_id: Optional[int] = None
    key_status: Optional[str] = None
    error: Optional[str] = None


class Alert(SQLModel, table=True):
    """倍率变化告警。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(index=True, foreign_key="site.id")
    domain: str = Field(index=True)
    created_at: datetime = Field(default_factory=_now, index=True)
    old_rate: Optional[float] = None
    new_rate: Optional[float] = None
    message: str = ""
    acknowledged: bool = Field(default=False, index=True)


class Setting(SQLModel, table=True):
    """全局键值配置。"""
    key: str = Field(primary_key=True)
    value: str = ""


# ----------------------------- API schema -----------------------------
class SiteCreate(BaseModel):
    domain: str
    email: str
    password: str
    remark: Optional[str] = None
    enabled: bool = True


class SiteUpdate(BaseModel):
    domain: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    remark: Optional[str] = None
    enabled: Optional[bool] = None


class SiteRead(BaseModel):
    """对外返回的站点信息，密码脱敏。"""
    id: int
    domain: str
    email: str
    remark: Optional[str] = None
    enabled: bool
    created_at: datetime
    has_password: bool = True

    @classmethod
    def from_site(cls, site: Site) -> "SiteRead":
        return cls(
            id=site.id,
            domain=site.domain,
            email=site.email,
            remark=site.remark,
            enabled=site.enabled,
            created_at=site.created_at,
            has_password=bool(site.password),
        )
