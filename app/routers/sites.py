"""站点管理接口（CRUD）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from .. import crud
from ..database import get_session
from ..models import SiteCreate, SiteRead, SiteUpdate

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.get("", response_model=list[SiteRead])
def list_sites(session: Session = Depends(get_session)):
    return [SiteRead.from_site(s) for s in crud.list_sites(session)]


@router.post("", response_model=SiteRead, status_code=201)
def create_site(data: SiteCreate, session: Session = Depends(get_session)):
    site = crud.create_site(session, data)
    return SiteRead.from_site(site)


@router.get("/{site_id}", response_model=SiteRead)
def get_site(site_id: int, session: Session = Depends(get_session)):
    site = crud.get_site(session, site_id)
    if not site:
        raise HTTPException(404, "站点不存在")
    return SiteRead.from_site(site)


@router.patch("/{site_id}", response_model=SiteRead)
def update_site(
    site_id: int, data: SiteUpdate, session: Session = Depends(get_session)
):
    site = crud.get_site(session, site_id)
    if not site:
        raise HTTPException(404, "站点不存在")
    return SiteRead.from_site(crud.update_site(session, site, data))


@router.delete("/{site_id}", status_code=204)
def delete_site(site_id: int, session: Session = Depends(get_session)):
    site = crud.get_site(session, site_id)
    if not site:
        raise HTTPException(404, "站点不存在")
    crud.delete_site(session, site)
