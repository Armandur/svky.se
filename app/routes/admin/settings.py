"""Admin-routes för redigering av webbplatsinnehåll.

Om-sidan, integritetssidan och nyhetssidan. Alla tre är markdown i
site_settings och delar redigeraren i admin/om_edit.html - skillnaden är
vilken nyckel som läses och vart den publika länken pekar.
"""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.csrf import get_csrf_secret, validate_csrf_token
from app.database import get_db
from app.deps import get_admin_or_redirect
from app.markdown_safe import render_markdown
from app.templating import NOTISNIVAER, templates

from .helpers import pending_takeover_count

router = APIRouter()


@router.get("/om")
async def admin_edit_om(request: Request):
    admin = get_admin_or_redirect(request)

    with get_db() as db:
        row = db.execute("SELECT value FROM site_settings WHERE key='about_content'").fetchone()
        takeovers = pending_takeover_count(db)

    return templates.TemplateResponse(
        "admin/om_edit.html",
        {
            "request": request,
            "user": admin,
            "content": row["value"] if row else "",
            "pending_takeovers": takeovers,
            "saved": request.query_params.get("saved") == "1",
            "page_title": "Om-sidan",
            "admin_path": "/admin/om",
            "public_path": "/om",
        },
    )


@router.post("/om")
async def admin_save_om(request: Request, content: str = Form(...), csrf_token: str = Form(...)):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    get_admin_or_redirect(request)

    with get_db() as db:
        db.execute(
            """INSERT INTO site_settings (key, value) VALUES ('about_content', ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (content,),
        )

    return RedirectResponse(url="/admin/om?saved=1", status_code=303)


@router.get("/nyheter")
async def admin_edit_nyheter(request: Request):
    admin = get_admin_or_redirect(request)

    with get_db() as db:
        row = db.execute("SELECT value FROM site_settings WHERE key='changelog_content'").fetchone()
        takeovers = pending_takeover_count(db)

    return templates.TemplateResponse(
        "admin/om_edit.html",
        {
            "request": request,
            "user": admin,
            "content": row["value"] if row else "",
            "pending_takeovers": takeovers,
            "saved": request.query_params.get("saved") == "1",
            "page_title": "Nyheter",
            "admin_path": "/admin/nyheter",
            "public_path": "/nyheter",
            # Bara nyhetssidan har en klippregel att förklara. Om-sidan och
            # integritetssidan visas i sin helhet, och en hjälptext om något
            # som inte gäller dem hade varit brus.
            "hjalptext": (
                "Skriv en <code>##</code>-rubrik per post, nyast överst. "
                "Startsidans ruta <strong>Senaste nytt</strong> visar allt fram "
                "till nästa <code>##</code>-rubrik, så text ovanför den första "
                "rubriken följer med. Bara <code>##</code> r\u00e4knas - "
                "<code>#</code> och <code>###</code> bryter inte. Saknas rubriker "
                "helt visas hela texten. Det finns inga datum bakom kulisserna: "
                "ordningen i texten \u00e4r ordningen, s\u00e5 skriv g\u00e4rna "
                "datumet i rubriken."
            ),
        },
    )


@router.post("/nyheter")
async def admin_save_nyheter(
    request: Request, content: str = Form(...), csrf_token: str = Form(...)
):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    get_admin_or_redirect(request)

    with get_db() as db:
        db.execute(
            """INSERT INTO site_settings (key, value) VALUES ('changelog_content', ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (content,),
        )

    return RedirectResponse(url="/admin/nyheter?saved=1", status_code=303)


@router.get("/notis")
async def admin_edit_notis(request: Request):
    admin = get_admin_or_redirect(request)

    with get_db() as db:
        rader = db.execute(
            "SELECT key, value FROM site_settings WHERE key IN ('notice_content', 'notice_level')"
        ).fetchall()
        takeovers = pending_takeover_count(db)
    varden = {r["key"]: r["value"] for r in rader}

    return templates.TemplateResponse(
        "admin/notis_edit.html",
        {
            "request": request,
            "user": admin,
            "content": varden.get("notice_content", ""),
            "niva": varden.get("notice_level", "info"),
            "nivaer": NOTISNIVAER,
            "pending_takeovers": takeovers,
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.get("/notis/forhandsvisning")
async def admin_notis_forhandsvisning(request: Request):
    """Bannern som den kommer att se ut, renderad AV SERVERN medan man skriver.

    Samma render_markdown som base.html sedan använder, alltså samma
    sanering. EasyMDE har en egen förhandsvisning inbyggd, men den ritar
    markdown med sin egen parser och kan därför visa en tagg som nh3 sedan
    stryper - och en banner som ser rätt ut i rutan men fel på sidan är
    värre än ingen förhandsvisning alls. Samma skäl som /swish-data: den
    som äger formatet ska räkna fram det.

    GET utan CSRF. Rutten ändrar ingenting och läser inte ens databasen -
    den tar texten ur frågesträngen och lämnar tillbaka den renderad.
    Adminspärren står kvar ändå, för resten av /admin gör det.

    `visas` säger om en banner alls skulle ritas. Tom text betyder ingen
    banner, och det är ett svar förhandsvisningen ska ge - inte en tom ruta
    som ser ut som att något gick sönder.
    """
    get_admin_or_redirect(request)

    text = (request.query_params.get("content") or "").strip()
    niva = request.query_params.get("niva") or "info"
    if niva not in NOTISNIVAER:
        niva = "info"

    if not text:
        return JSONResponse({"visas": False, "html": "", "niva": niva})

    return JSONResponse({"visas": True, "html": str(render_markdown(text)), "niva": niva})


@router.post("/notis")
async def admin_save_notis(
    request: Request,
    content: str = Form(""),
    niva: str = Form("info"),
    csrf_token: str = Form(...),
):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    get_admin_or_redirect(request)

    # Nivån kommer från ett formulär och är därmed indata utifrån, även om
    # den ser ut som ett val mellan två knappar. Ett okänt värde blir info
    # och inte ett fel: bannern ska visas, det är hela poängen med den.
    if niva not in NOTISNIVAER:
        niva = "info"

    with get_db() as db:
        for nyckel, varde in (("notice_content", content), ("notice_level", niva)):
            db.execute(
                """INSERT INTO site_settings (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (nyckel, varde),
            )

    return RedirectResponse(url="/admin/notis?saved=1", status_code=303)


@router.get("/integritet")
async def admin_edit_integritet(request: Request):
    admin = get_admin_or_redirect(request)

    with get_db() as db:
        row = db.execute(
            "SELECT value FROM site_settings WHERE key='integritet_content'"
        ).fetchone()
        takeovers = pending_takeover_count(db)

    return templates.TemplateResponse(
        "admin/om_edit.html",
        {
            "request": request,
            "user": admin,
            "content": row["value"] if row else "",
            "pending_takeovers": takeovers,
            "saved": request.query_params.get("saved") == "1",
            "page_title": "Integritetssidan",
            "admin_path": "/admin/integritet",
            "public_path": "/integritet",
        },
    )


@router.post("/integritet")
async def admin_save_integritet(
    request: Request, content: str = Form(...), csrf_token: str = Form(...)
):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    get_admin_or_redirect(request)

    with get_db() as db:
        db.execute(
            """INSERT INTO site_settings (key, value) VALUES ('integritet_content', ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (content,),
        )

    return RedirectResponse(url="/admin/integritet?saved=1", status_code=303)
