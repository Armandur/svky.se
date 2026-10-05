"""Nollställning av klickstatistik för en kortlänk.

Samma mönster som engångslänkarna: GET visar bara vad som skulle raderas,
POST med CSRF gör det. Siffrorna på bekräftelsesidan räknas ur samma rader
som sedan raderas, så admin ser utfallet innan transaktionen görs.
"""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.csrf import get_csrf_secret, validate_csrf_token
from app.database import get_db
from app.deps import get_admin_or_redirect
from app.templating import templates

from .helpers import pending_takeover_count

router = APIRouter()


def _klickoversikt(db, link_id: int) -> dict:
    rad = db.execute(
        """SELECT COUNT(*) AS totalt,
                  COALESCE(SUM(clicked_at >= datetime('now', '-7 days')), 0) AS senaste_7d,
                  COALESCE(SUM(clicked_at >= datetime('now', '-30 days')), 0) AS senaste_30d,
                  MIN(clicked_at) AS forsta,
                  MAX(clicked_at) AS sista
           FROM clicks WHERE link_id=?""",
        (link_id,),
    ).fetchone()
    return dict(rad)


@router.get("/links/{link_id}/nollstall-klick")
async def nollstall_klick_bekrafta(request: Request, link_id: int):
    admin = get_admin_or_redirect(request)
    with get_db() as db:
        link = db.execute("SELECT id, code FROM links WHERE id=?", (link_id,)).fetchone()
        if not link:
            raise HTTPException(status_code=404)
        oversikt = _klickoversikt(db, link_id)
        takeovers = pending_takeover_count(db)
    return templates.TemplateResponse(
        "admin/klick_nollstall.html",
        {
            "request": request,
            "user": admin,
            "link": dict(link),
            "oversikt": oversikt,
            "pending_takeovers": takeovers,
        },
    )


@router.post("/links/{link_id}/nollstall-klick")
async def nollstall_klick(request: Request, link_id: int, csrf_token: str = Form(...)):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    admin = get_admin_or_redirect(request)
    with get_db() as db:
        link = db.execute("SELECT id FROM links WHERE id=?", (link_id,)).fetchone()
        if not link:
            raise HTTPException(status_code=404)
        antal = db.execute("DELETE FROM clicks WHERE link_id=?", (link_id,)).rowcount
        db.execute("UPDATE links SET last_used_at=NULL WHERE id=?", (link_id,))
        db.execute(
            "INSERT INTO audit_log (action, actor_id, link_id, detail) VALUES (?,?,?,?)",
            ("admin_nollstall_klick", admin["id"], link_id, f"{antal} klick raderade"),
        )
    return RedirectResponse(url=f"/admin/links/{link_id}?nollstallt={antal}", status_code=303)
