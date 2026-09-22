"""Admin-routes för gravplatsernas sökvägar (TASK-2145).

Bara det som låset kräver: en lista och ett byte av sökväg. Nodträdet
redigeras inte härifrån - den ytan hör till importen (TASK-2146) och
QR-uttaget (TASK-2147), och en halv trädredigerare hade blivit en yta att
underhålla utan att någon kan använda den än.
"""

from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.csrf import get_csrf_secret, validate_csrf_token
from app.database import get_db
from app.deps import get_admin_or_redirect
from app.gravplats import Gravplatsfel, satt_sokvag
from app.templating import templates

from .helpers import pending_takeover_count

router = APIRouter()


def _tillbaka(msg: str = "", sparat: bool = False) -> RedirectResponse:
    if msg:
        return RedirectResponse(url=f"/admin/gravplatser?error={quote(msg)}", status_code=303)
    return RedirectResponse(
        url="/admin/gravplatser" + ("?saved=1" if sparat else ""), status_code=303
    )


@router.get("/gravplatser")
async def admin_gravplatser(request: Request):
    admin = get_admin_or_redirect(request)
    with get_db() as db:
        rader = db.execute(
            """SELECT g.id, g.sokvag, g.nummer, g.tryckt_at, n.namn AS nod_namn,
                      (SELECT COUNT(*) FROM gravplats_views v WHERE v.gravplats_id = g.id)
                        AS visningar
               FROM gravplatser g
               LEFT JOIN gravnoder n ON n.id = g.nod_id
               ORDER BY g.sokvag
               LIMIT 500"""  # TODO: sidindelning före bulkimporten (TASK-2146)
        ).fetchall()
        takeovers = pending_takeover_count(db)

    return templates.TemplateResponse(
        "admin/gravplatser.html",
        {
            "request": request,
            "user": admin,
            "gravplatser": rader,
            "pending_takeovers": takeovers,
            "error": request.query_params.get("error") or "",
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/gravplatser/{gravplats_id}/sokvag")
async def admin_gravplats_sokvag(
    request: Request,
    gravplats_id: int,
    sokvag: str = Form(...),
    csrf_token: str = Form(...),
):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    get_admin_or_redirect(request)

    with get_db() as db:
        try:
            satt_sokvag(db, gravplats_id, sokvag)
        except Gravplatsfel as fel:
            return _tillbaka(str(fel))
    return _tillbaka(sparat=True)
