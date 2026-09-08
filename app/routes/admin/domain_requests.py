"""Adminhantering av ansökningar om externa mål-URL:er."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.config import BASE_URL
from app.csrf import get_csrf_secret, validate_csrf_token
from app.database import get_db
from app.deps import get_admin_or_redirect
from app.mail import MailError, skicka_domanansokan_avslagen, skicka_domanansokan_godkand
from app.templating import templates

from .helpers import pending_takeover_count

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/domanansokningar")
async def admin_domain_requests(request: Request):
    admin = get_admin_or_redirect(request)
    with get_db() as db:
        requests = db.execute(
            """SELECT dpr.id, dpr.permission, dpr.reason, dpr.status,
                      dpr.created_at, dpr.resolved_at, u.email
                 FROM domain_permission_requests dpr
                 JOIN users u ON u.id=dpr.user_id
                ORDER BY dpr.status='pending' DESC, dpr.created_at DESC"""
        ).fetchall()
        pending_takeovers = pending_takeover_count(db)

    return templates.TemplateResponse(
        "admin/domain_requests.html",
        {
            "request": request,
            "user": admin,
            "domain_requests": [dict(row) for row in requests],
            "pending_takeovers": pending_takeovers,
        },
    )


def _resolve_request(req_id: int, action: str, admin_id: int) -> tuple[str, str]:
    now = datetime.now(UTC).replace(tzinfo=None).isoformat()
    with get_db() as db:
        row = db.execute(
            """SELECT dpr.id, dpr.user_id, dpr.permission, dpr.status, u.email
                 FROM domain_permission_requests dpr
                 JOIN users u ON u.id=dpr.user_id
                WHERE dpr.id=?""",
            (req_id,),
        ).fetchone()
        if not row or row["status"] != "pending":
            raise HTTPException(status_code=404)
        if row["permission"] != "external_urls":
            raise HTTPException(status_code=400)

        if action == "approved":
            db.execute("UPDATE users SET allow_external_urls=1 WHERE id=?", (row["user_id"],))
        db.execute(
            """UPDATE domain_permission_requests
                  SET status=?, resolved_at=? WHERE id=?""",
            (action, now, req_id),
        )
        db.execute(
            "INSERT INTO audit_log (action, actor_id, detail) VALUES (?, ?, ?)",
            (
                f"domain_permission_{action}",
                admin_id,
                f"{row['email']}: external_urls",
            ),
        )
    return row["email"], action


def _send_decision(email: str, action: str) -> None:
    try:
        if action == "approved":
            skicka_domanansokan_godkand(email, BASE_URL)
        else:
            skicka_domanansokan_avslagen(email)
    except MailError:
        log.exception("Kunde inte skicka besked om domänansökan")


@router.post("/domanansokningar/{req_id}/approve")
async def approve_domain_request(request: Request, req_id: int, csrf_token: str = Form(...)):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    admin = get_admin_or_redirect(request)
    email, action = _resolve_request(req_id, "approved", admin["id"])
    _send_decision(email, action)
    return RedirectResponse(url="/admin/domanansokningar?beslut=godkand", status_code=303)


@router.post("/domanansokningar/{req_id}/reject")
async def reject_domain_request(request: Request, req_id: int, csrf_token: str = Form(...)):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    admin = get_admin_or_redirect(request)
    email, action = _resolve_request(req_id, "rejected", admin["id"])
    _send_decision(email, action)
    return RedirectResponse(url="/admin/domanansokningar?beslut=avslagen", status_code=303)
