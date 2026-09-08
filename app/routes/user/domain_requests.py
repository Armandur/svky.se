"""Användarens ansökan om rätt att länka till externa domäner."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.csrf import get_csrf_secret, validate_csrf_token
from app.database import get_db
from app.deps import get_user_or_redirect
from app.templating import templates
from app.validation import MAX_TEXT_LENGTH, validate_length

router = APIRouter()


@router.get("/mina-lankar/domanansokan")
async def domain_request_form(request: Request):
    user = get_user_or_redirect(request)
    with get_db() as db:
        pending = db.execute(
            """SELECT id, reason, created_at
                 FROM domain_permission_requests
                WHERE user_id=? AND permission='external_urls' AND status='pending'""",
            (user["id"],),
        ).fetchone()

    return templates.TemplateResponse(
        "domain_request.html",
        {
            "request": request,
            "user": user,
            "pending_request": dict(pending) if pending else None,
        },
    )


@router.post("/mina-lankar/domanansokan")
async def create_domain_request(
    request: Request,
    reason: str = Form(...),
    csrf_token: str = Form(...),
):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    user = get_user_or_redirect(request)
    reason = reason.strip()

    error = None
    if not reason:
        error = "Skriv varför du behöver länka till en extern domän."
    elif length_error := validate_length(reason, MAX_TEXT_LENGTH, "Motiveringen"):
        error = length_error
    if error:
        return templates.TemplateResponse(
            "domain_request.html",
            {
                "request": request,
                "user": user,
                "pending_request": None,
                "error": error,
                "reason": reason,
            },
            status_code=422,
        )

    with get_db() as db:
        already_allowed = db.execute(
            "SELECT allow_external_urls FROM users WHERE id=?", (user["id"],)
        ).fetchone()
        if already_allowed and already_allowed["allow_external_urls"]:
            return RedirectResponse(
                url="/mina-lankar/domanansokan?redan_behorig=1", status_code=303
            )
        result = db.execute(
            """INSERT INTO domain_permission_requests (user_id, permission, reason)
               SELECT ?, 'external_urls', ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM domain_permission_requests
                     WHERE user_id=? AND permission='external_urls' AND status='pending'
                )""",
            (user["id"], reason, user["id"]),
        )
        if result.rowcount == 0:
            return RedirectResponse(url="/mina-lankar/domanansokan?vantar=1", status_code=303)

    return RedirectResponse(url="/mina-lankar/domanansokan?skickad=1", status_code=303)
