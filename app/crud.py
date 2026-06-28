"""数据库操作：站点 CRUD、快照写入/查询、告警写入/查询。"""
from typing import Optional

from sqlmodel import Session, select

from .models import Alert, PriceSnapshot, Setting, Site, SiteCreate, SiteUpdate


# ----------------------------- Site CRUD -----------------------------
def list_sites(session: Session, only_enabled: bool = False) -> list[Site]:
    stmt = select(Site)
    if only_enabled:
        stmt = stmt.where(Site.enabled == True)  # noqa: E712
    return list(session.exec(stmt.order_by(Site.id)).all())


def get_site(session: Session, site_id: int) -> Optional[Site]:
    return session.get(Site, site_id)


def create_site(session: Session, data: SiteCreate) -> Site:
    site = Site(**data.model_dump())
    session.add(site)
    session.commit()
    session.refresh(site)
    return site


def update_site(session: Session, site: Site, data: SiteUpdate) -> Site:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(site, field, value)
    session.add(site)
    session.commit()
    session.refresh(site)
    return site


def delete_site(session: Session, site: Site) -> None:
    session.delete(site)
    session.commit()


def update_site_token(session: Session, site: Site, token: str) -> Site:
    site.token = token
    session.add(site)
    session.commit()
    session.refresh(site)
    return site


# ----------------------------- Snapshot -----------------------------
def add_snapshot(session: Session, data: dict) -> PriceSnapshot:
    snap = PriceSnapshot(
        site_id=data["site_id"],
        domain=data["domain"],
        balance=data.get("balance"),
        group_name=data.get("group_name"),
        rate_multiplier=data.get("rate_multiplier"),
        key_name=data.get("key_name"),
        key_id=data.get("key_id"),
        key_status=data.get("key_status"),
        error=data.get("error"),
        fetched_at=data.get("fetched_at"),
    )
    session.add(snap)
    session.commit()
    session.refresh(snap)
    return snap


def last_successful_snapshot(
    session: Session, site_id: int, key_name: str, before_id: Optional[int] = None
) -> Optional[PriceSnapshot]:
    """该站点+key 最近一条成功（rate_multiplier 非空）的快照，用于告警比对。"""
    stmt = (
        select(PriceSnapshot)
        .where(PriceSnapshot.site_id == site_id)
        .where(PriceSnapshot.key_name == key_name)
        .where(PriceSnapshot.rate_multiplier != None)  # noqa: E711
    )
    if before_id is not None:
        stmt = stmt.where(PriceSnapshot.id < before_id)
    stmt = stmt.order_by(PriceSnapshot.id.desc())
    return session.exec(stmt).first()


def list_snapshots(
    session: Session, site_id: Optional[int] = None, limit: int = 100
) -> list[PriceSnapshot]:
    stmt = select(PriceSnapshot)
    if site_id is not None:
        stmt = stmt.where(PriceSnapshot.site_id == site_id)
    stmt = stmt.order_by(PriceSnapshot.id.desc()).limit(limit)
    return list(session.exec(stmt).all())


def latest_snapshots_per_site(session: Session) -> dict[int, list[PriceSnapshot]]:
    """每个站点最近一次抓取的所有 key 快照（可能有多个 key）。"""
    stmt = select(PriceSnapshot).order_by(PriceSnapshot.id.desc())
    result: dict[int, list[PriceSnapshot]] = {}
    seen: set[int] = set()
    for snap in session.exec(stmt).all():
        if snap.site_id not in seen:
            seen.add(snap.site_id)
            latest_ts = snap.fetched_at
        # 同一站点、同一次抓取的 key 共享相同 fetched_at
        if snap.fetched_at == latest_ts:
            result.setdefault(snap.site_id, []).append(snap)
    return result


# ----------------------------- Alert -----------------------------
def add_alert(
    session: Session,
    site_id: int,
    domain: str,
    old_rate: Optional[float],
    new_rate: Optional[float],
    message: str,
) -> Alert:
    alert = Alert(
        site_id=site_id,
        domain=domain,
        old_rate=old_rate,
        new_rate=new_rate,
        message=message,
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def list_alerts(
    session: Session, acknowledged: Optional[bool] = None, limit: int = 100
) -> list[Alert]:
    stmt = select(Alert)
    if acknowledged is not None:
        stmt = stmt.where(Alert.acknowledged == acknowledged)
    stmt = stmt.order_by(Alert.id.desc()).limit(limit)
    return list(session.exec(stmt).all())


def ack_alert(session: Session, alert: Alert) -> Alert:
    alert.acknowledged = True
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


# ----------------------------- Setting -----------------------------
def get_setting(session: Session, key: str) -> Optional[Setting]:
    return session.get(Setting, key)


def set_setting(session: Session, key: str, value: str) -> Setting:
    setting = session.get(Setting, key)
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
    session.add(setting)
    session.commit()
    session.refresh(setting)
    return setting


def list_settings(session: Session) -> list[Setting]:
    return list(session.exec(select(Setting)).all())
