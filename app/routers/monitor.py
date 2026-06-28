"""监控数据接口：手动抓取、快照查询、告警查询、配置管理、key 启用禁用。"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session

from .. import crud
from ..database import get_session
from ..fetcher import set_key_status
from ..models import Alert, PriceSnapshot
from ..scheduler import reschedule, run_fetch_cycle
from sqlmodel import func, select

router = APIRouter(prefix="/api", tags=["monitor"])


@router.get("/monitor/version")
def monitor_version(session: Session = Depends(get_session)):
    """轻量轮询接口：返回最新快照数，前端检测变化后自动刷新。"""
    count = session.exec(select(func.count(PriceSnapshot.id))).one()
    return {"snapshot_count": count}


@router.post("/monitor/run")
async def manual_run():
    """手动触发一次抓取，返回本次结果。"""
    results = await run_fetch_cycle()
    return {"count": len(results), "results": results}


@router.get("/snapshots", response_model=list[PriceSnapshot])
def list_snapshots(
    site_id: Optional[int] = None,
    limit: int = Query(100, le=1000),
    session: Session = Depends(get_session),
):
    return crud.list_snapshots(session, site_id=site_id, limit=limit)


@router.get("/alerts", response_model=list[Alert])
def list_alerts(
    acknowledged: Optional[bool] = None,
    limit: int = Query(100, le=1000),
    session: Session = Depends(get_session),
):
    return crud.list_alerts(session, acknowledged=acknowledged, limit=limit)


@router.post("/alerts/{alert_id}/ack", response_model=Alert)
def ack_alert(alert_id: int, session: Session = Depends(get_session)):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "告警不存在")
    return crud.ack_alert(session, alert)


# ----------------------------- Key 启用 / 禁用 -----------------------------
class KeyStatusUpdate(BaseModel):
    status: str  # "active" 或 "inactive"


@router.post("/keys/{site_id}/{key_id}/enable")
async def enable_key(site_id: int, key_id: int, session: Session = Depends(get_session)):
    """手动启用上游 key。"""
    site = crud.get_site(session, site_id)
    if not site:
        raise HTTPException(404, "站点不存在")
    if not site.token:
        raise HTTPException(400, "站点无缓存 token，请先执行一次抓取")
    ok = await set_key_status(
        {"domain": site.domain, "token": site.token},
        key_id,
        "active",
    )
    if not ok:
        raise HTTPException(500, "上游 API 调用失败")
    return {"status": "ok", "key_id": key_id, "new_status": "active"}


@router.post("/keys/{site_id}/{key_id}/disable")
async def disable_key(site_id: int, key_id: int, session: Session = Depends(get_session)):
    """手动禁用上游 key。"""
    site = crud.get_site(session, site_id)
    if not site:
        raise HTTPException(404, "站点不存在")
    if not site.token:
        raise HTTPException(400, "站点无缓存 token，请先执行一次抓取")
    ok = await set_key_status(
        {"domain": site.domain, "token": site.token},
        key_id,
        "inactive",
    )
    if not ok:
        raise HTTPException(500, "上游 API 调用失败")
    return {"status": "ok", "key_id": key_id, "new_status": "inactive"}


# ----------------------------- Settings -----------------------------
class IntervalUpdate(BaseModel):
    seconds: int


@router.get("/settings")
def get_settings(session: Session = Depends(get_session)):
    settings = crud.list_settings(session)
    return {s.key: s.value for s in settings}


@router.put("/settings/fetch-interval")
def update_fetch_interval(
    data: IntervalUpdate,
    session: Session = Depends(get_session),
):
    if data.seconds < 1:
        raise HTTPException(400, "间隔必须 >= 1 秒")
    crud.set_setting(session, "fetch_interval", str(data.seconds))
    reschedule(data.seconds)
    return {"fetch_interval": data.seconds}
