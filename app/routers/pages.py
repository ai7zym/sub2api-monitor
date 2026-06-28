"""网页界面（Jinja2 服务端渲染）。"""
import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from .. import config, crud
from ..database import get_session
from ..models import SiteCreate, SiteUpdate

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

router = APIRouter(tags=["pages"])


@router.get("/setup")
def setup_page(request: Request):
    """初始化向导页面（无需登录）。"""
    if config.is_initialized():
        return RedirectResponse("/", 302)
    return templates.TemplateResponse(request, "setup.html", {})


@router.get("/")
def index(request: Request, session: Session = Depends(get_session)):
    if not config.is_initialized():
        return RedirectResponse("/setup", 302)
    sites = crud.list_sites(session)
    latest = crud.latest_snapshots_per_site(session)
    _colors = [
        "blue", "amber", "emerald", "violet", "rose", "cyan",
    ]
    # 按站点分组的数据，同时支持桌面表格和移动卡片
    site_cards = []
    table_rows = []
    for i, s in enumerate(sites):
        snaps = latest.get(s.id, []) or [None]
        color = _colors[i % len(_colors)]
        site_cards.append({
            "site": s,
            "snaps": [x for x in snaps if x],
            "color": color,
            "site_token": s.token,
        })
        for snap in snaps:
            table_rows.append({
                "site": s,
                "snap": snap,
                "rowspan": len(snaps),
                "is_first": snap == (snaps[0] if snaps else None),
                "bg": f"bg-{color}-50/60",
                "site_token": s.token,
            })
    alerts = crud.list_alerts(session, limit=20)
    interval = config.FETCH_INTERVAL_SECONDS
    setting = crud.get_setting(session, "fetch_interval")
    if setting and setting.value:
        try:
            interval = int(setting.value)
        except ValueError:
            pass
    return templates.TemplateResponse(
        request, "index.html", {
            "site_cards": site_cards,
            "table_rows": table_rows,
            "alerts": alerts,
            "interval": interval,
        }
    )


@router.get("/sites")
def sites_page(request: Request, session: Session = Depends(get_session)):
    sites = crud.list_sites(session)
    return templates.TemplateResponse(request, "sites.html", {"sites": sites})


@router.post("/sites/create")
def sites_create(
    domain: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    remark: str = Form(""),
    enabled: bool = Form(False),
    session: Session = Depends(get_session),
):
    crud.create_site(
        session,
        SiteCreate(
            domain=domain.strip(),
            email=email.strip(),
            password=password,
            remark=remark.strip() or None,
            enabled=enabled,
        ),
    )
    return RedirectResponse("/sites", status_code=303)


@router.post("/sites/{site_id}/update")
def sites_update(
    site_id: int,
    domain: str = Form(...),
    email: str = Form(...),
    password: str = Form(""),
    remark: str = Form(""),
    enabled: bool = Form(False),
    session: Session = Depends(get_session),
):
    site = crud.get_site(session, site_id)
    if site:
        data = SiteUpdate(
            domain=domain.strip(),
            email=email.strip(),
            remark=remark.strip() or None,
            enabled=enabled,
        )
        if password:  # 留空则不修改密码
            data.password = password
        crud.update_site(session, site, data)
    return RedirectResponse("/sites", status_code=303)


@router.post("/sites/{site_id}/delete")
def sites_delete(site_id: int, session: Session = Depends(get_session)):
    site = crud.get_site(session, site_id)
    if site:
        crud.delete_site(session, site)
    return RedirectResponse("/sites", status_code=303)
