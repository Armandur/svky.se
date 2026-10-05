"""Flytta alla länkar och samlingar från en användare till en annan.

GET visar vad som flyttas och till vem, POST med CSRF gör det. Förut gick
formuläret rakt på POST: en felskriven adress skapade ett nytt konto och
flyttade allt dit utan att admin såg vad som skulle hända.
"""

from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.csrf import get_csrf_secret, validate_csrf_token
from app.database import get_db
from app.deps import get_admin_or_redirect
from app.templating import templates
from app.validation import validate_email

from .helpers import pending_takeover_count

router = APIRouter()


def _flyttoversikt(db, user_id: int, new_email: str) -> dict:
    links = db.execute(
        "SELECT code, status FROM links WHERE owner_id=? ORDER BY code", (user_id,)
    ).fetchall()
    bundles = db.execute(
        "SELECT code, name, status FROM bundles WHERE owner_id=? ORDER BY code", (user_id,)
    ).fetchall()
    mottagare = db.execute(
        """SELECT id, is_admin,
                  (SELECT COUNT(*) FROM links WHERE owner_id=u.id) AS antal_lankar,
                  (SELECT COUNT(*) FROM bundles WHERE owner_id=u.id) AS antal_samlingar
           FROM users u WHERE email=?""",
        (new_email,),
    ).fetchone()
    return {
        "links": [dict(r) for r in links],
        "bundles": [dict(r) for r in bundles],
        "mottagare": dict(mottagare) if mottagare else None,
    }


def _fel(msg: str) -> RedirectResponse:
    return RedirectResponse(url="/admin/users?" + urlencode({"delete_error": msg}), status_code=303)


def _kontrollera(db, user_id: int, new_email: str) -> tuple[dict, str | None]:
    """Returnerar (avsändarrad, felmeddelande). Samma regler för GET och POST."""
    old_user = db.execute("SELECT id, email FROM users WHERE id=?", (user_id,)).fetchone()
    if not old_user:
        raise HTTPException(status_code=404)
    fel = validate_email(new_email, allow_any_domain=True)
    if fel:
        return dict(old_user), fel
    if new_email == old_user["email"].lower():
        return dict(old_user), "Mottagaren kan inte vara samma konto som avsändaren."
    return dict(old_user), None


@router.get("/users/{user_id}/flytta-allt")
async def flytta_allt_bekrafta(request: Request, user_id: int, new_email: str = ""):
    admin = get_admin_or_redirect(request)
    new_email = new_email.strip().lower()
    with get_db() as db:
        old_user, fel = _kontrollera(db, user_id, new_email)
        if fel:
            return _fel(fel)
        oversikt = _flyttoversikt(db, user_id, new_email)
        takeovers = pending_takeover_count(db)
    return templates.TemplateResponse(
        "admin/flytta_allt.html",
        {
            "request": request,
            "user": admin,
            "fran": old_user,
            "till": new_email,
            "pending_takeovers": takeovers,
            **oversikt,
        },
    )


@router.post("/users/{user_id}/transfer-all")
async def admin_transfer_all(
    request: Request,
    user_id: int,
    new_email: str = Form(...),
    csrf_token: str = Form(...),
):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    admin = get_admin_or_redirect(request)
    new_email = new_email.strip().lower()

    with get_db() as db:
        old_user, fel = _kontrollera(db, user_id, new_email)
        if fel:
            return _fel(fel)

        db.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (new_email,))
        new_user = db.execute("SELECT id FROM users WHERE email=?", (new_email,)).fetchone()

        link_rows = db.execute("SELECT id FROM links WHERE owner_id=?", (user_id,)).fetchall()
        bundle_rows = db.execute(
            "SELECT id, code FROM bundles WHERE owner_id=?", (user_id,)
        ).fetchall()

        db.execute("UPDATE links SET owner_id=? WHERE owner_id=?", (new_user["id"], user_id))
        db.execute(
            "UPDATE bundles SET owner_id=?, updated_at=CURRENT_TIMESTAMP WHERE owner_id=?",
            (new_user["id"], user_id),
        )

        for link in link_rows:
            db.execute(
                "INSERT INTO audit_log (action, actor_id, link_id, detail) VALUES (?,?,?,?)",
                (
                    "transfer",
                    admin["id"],
                    link["id"],
                    f"bulk move from {old_user['email']} to {new_email}",
                ),
            )
        for bundle in bundle_rows:
            db.execute(
                "INSERT INTO audit_log (action, actor_id, detail) VALUES (?,?,?)",
                (
                    "admin_bundle_transfer",
                    admin["id"],
                    f"bundle:{bundle['id']} (kod={bundle['code']}) bulk-överflytt från {old_user['email']} till {new_email}",
                ),
            )

    return RedirectResponse(url="/admin/users", status_code=303)
