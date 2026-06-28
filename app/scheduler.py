"""定时抓取与告警判定。"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session

from . import config, crud
from .database import get_engine
from .fetcher import fetch_all, set_key_status
from .mail import send_alert_email
from .models import Setting, _now

logger = logging.getLogger("price_monitor")

scheduler = AsyncIOScheduler()


async def run_fetch_cycle() -> list[dict]:
    """执行一次完整抓取周期，返回本次抓取结果列表。"""
    eng = get_engine()
    with Session(eng) as session:
        sites = crud.list_sites(session, only_enabled=True)
        site_dicts = [
            {
                "id": s.id,
                "domain": s.domain,
                "email": s.email,
                "password": s.password,
                "token": s.token,
            }
            for s in sites
        ]

    if not site_dicts:
        logger.info("没有启用的站点，跳过抓取")
        return []

    logger.info("开始抓取 %d 个站点", len(site_dicts))
    results, token_updates = await fetch_all(site_dicts)

    if token_updates:
        with Session(eng) as session:
            for site_id, new_token in token_updates.items():
                site = crud.get_site(session, site_id)
                if site:
                    crud.update_site_token(session, site, new_token)

    batch_time = _now()
    for r in results:
        r["fetched_at"] = batch_time

    webhook_payloads: list[dict] = []

    with Session(eng) as session:
        for res in results:
            snap = crud.add_snapshot(session, res)

            new_rate = res.get("rate_multiplier")
            key_name = res.get("key_name")
            if new_rate is None or key_name is None:
                continue
            prev = crud.last_successful_snapshot(
                session, res["site_id"], key_name, before_id=snap.id
            )
            if prev is None or prev.rate_multiplier is None:
                continue
            if prev.rate_multiplier != new_rate:
                is_up = new_rate > prev.rate_multiplier
                msg = (
                    f"{res['domain']}/{key_name} 倍率{'上涨' if is_up else '下跌'}: "
                    f"{prev.rate_multiplier} -> {new_rate}"
                )
                crud.add_alert(
                    session,
                    site_id=res["site_id"],
                    domain=res["domain"],
                    old_rate=prev.rate_multiplier,
                    new_rate=new_rate,
                    message=msg,
                )
                logger.warning(msg)
                webhook_payloads.append(
                    {
                        "domain": res["domain"],
                        "old_rate": prev.rate_multiplier,
                        "new_rate": new_rate,
                        "message": msg,
                    }
                )

                if is_up and res.get("key_id"):
                    site_token = next(
                        (s["token"] for s in site_dicts if s["id"] == res["site_id"]),
                        None,
                    )
                    if site_token:
                        ok = await set_key_status(
                            {"domain": res["domain"], "token": site_token},
                            res["key_id"],
                            "inactive",
                        )
                        if ok:
                            logger.info(
                                "已自动禁用 %s/%s (key_id=%d)",
                                res["domain"], key_name, res["key_id"],
                            )

    if config.ALERT_EMAIL_TO and webhook_payloads:
        _send_batch_email(webhook_payloads, config.ALERT_EMAIL_TO, batch_time)

    logger.info("抓取完成")
    return results


def _send_batch_email(payloads: list[dict], recipients: list[str], batch_time) -> None:
    if not payloads:
        return
    items_html = ""
    for p in payloads:
        direction = "上涨" if p["new_rate"] > p["old_rate"] else "下跌"
        color = "#dc2626" if p["new_rate"] > p["old_rate"] else "#16a34a"
        items_html += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{p['domain']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{p['old_rate']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;color:{color};font-weight:600;">{p['new_rate']} ({direction})</td>
        </tr>"""

    ts = batch_time.strftime("%Y-%m-%d %H:%M:%S") if batch_time else ""
    body = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,Segoe UI,Microsoft YaHei,sans-serif;padding:20px;background:#f3f4f6;">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
  <div style="background:#111827;color:#fff;padding:16px 20px;font-size:16px;font-weight:600;">
    上游价格监控 - 倍率变化告警
  </div>
  <div style="padding:20px;">
    <p style="margin:0 0 16px;font-size:14px;color:#374151;">以下 {len(payloads)} 个站点/Key 倍率发生变化：</p>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead><tr style="background:#f9fafb;">
        <th style="text-align:left;padding:8px 12px;color:#6b7280;font-weight:500;">域名</th>
        <th style="text-align:left;padding:8px 12px;color:#6b7280;font-weight:500;">原倍率</th>
        <th style="text-align:left;padding:8px 12px;color:#6b7280;font-weight:500;">新倍率</th>
      </tr></thead>
      <tbody>{items_html}</tbody>
    </table>
    <p style="margin:16px 0 0;font-size:12px;color:#9ca3af;">抓取时间: {ts}</p>
  </div>
</div>
</body></html>"""

    send_alert_email(
        subject=f"[价格监控] {len(payloads)} 个倍率变化",
        body_html=body,
        to_addrs=recipients,
    )


def _load_interval() -> int:
    eng = get_engine()
    try:
        with Session(eng) as session:
            setting = session.get(Setting, "fetch_interval")
            if setting and setting.value:
                return int(setting.value)
    except Exception:
        pass
    return config.FETCH_INTERVAL_SECONDS


def start_scheduler() -> None:
    interval = _load_interval()
    scheduler.add_job(
        run_fetch_cycle,
        trigger=IntervalTrigger(seconds=interval),
        id="fetch_cycle",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=interval,
    )
    scheduler.start()
    logger.info("调度器已启动，每 %d 秒抓取一次", interval)


def reschedule(new_seconds: int) -> None:
    scheduler.reschedule_job(
        "fetch_cycle",
        trigger=IntervalTrigger(seconds=new_seconds),
        misfire_grace_time=new_seconds,
    )
    logger.info("抓取间隔已更新为 %d 秒", new_seconds)


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
