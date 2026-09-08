"""Publik läs/redirect-router.

Innehåller enbart read-only endpoints och catch-all redirect:
  GET /          - startsida med snabblänkar
  GET /om        - om-sidan (markdown)
  GET /integritet - integritetssidan (markdown)
  GET /nyheter    - vad som ändrats i tjänsten (markdown)
  GET /{code}    - redirect/bundle-visning (catch-all, måste vara sist)

Beställningsflöde → app/routes/orders.py
Takeover-formulär → app/routes/takeovers.py
Överlåtelsebekräftelse → app/routes/transfers.py
"""

from collections import defaultdict
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app import qr
from app.auth import get_current_user
from app.config import BASE_URL, RESERVED_CODES, LinkStatus
from app.database import get_db
from app.markdown_safe import render_markdown
from app.swish import (
    REDIGERBAR_MOTTAGARE,
    REDIGERBART_BELOPP,
    REDIGERBART_MEDDELANDE,
    Swishbetalning,
    Swishfel,
    applank,
    qr_strang,
)
from app.templating import templates

router = APIRouter()


@router.get("/")
async def index(request: Request):
    user = get_current_user(request)
    with get_db() as db:
        link_featured = db.execute(
            """SELECT id, code, note, featured_title, featured_icon,
                      featured_sort AS sort_order, created_at
               FROM links
               WHERE is_featured=1 AND status=1""",
        ).fetchall()
        ext_featured = db.execute(
            """SELECT id, title, url, icon, sort_order, created_at
               FROM featured_external""",
        ).fetchall()
        intro_row = db.execute(
            "SELECT value FROM site_settings WHERE key='snabblänkar_intro'"
        ).fetchone()
        heading_row = db.execute(
            "SELECT value FROM site_settings WHERE key='snabblänkar_heading'"
        ).fetchone()
        subtitle_row = db.execute(
            "SELECT value FROM site_settings WHERE key='snabblänkar_subtitle'"
        ).fetchone()
        nyhet_row = db.execute(
            "SELECT value FROM site_settings WHERE key='changelog_content'"
        ).fetchone()

    intro_md = intro_row["value"] if intro_row else ""
    featured_intro_html = render_markdown(intro_md) if intro_md else None

    senaste_md = _senaste_nyhet(nyhet_row["value"] if nyhet_row else "")
    senaste_nyhet_html = render_markdown(senaste_md) if senaste_md else None

    # Saknad rad → defaulttext. Sparat tomt värde → dölj raden helt.
    featured_heading = heading_row["value"] if heading_row is not None else "Snabblänkar"
    featured_subtitle = (
        subtitle_row["value"] if subtitle_row is not None else "Ofta använda kortlänkar"
    )

    # Slå ihop link-baserade och externa snabblänkar till en enad lista.
    featured: list[dict] = []
    for r in link_featured:
        featured.append(
            {
                "external": False,
                "href": f"/{r['code']}",
                "title": r["featured_title"] or r["note"] or r["code"],
                "subtitle": f"svky.se/{r['code']}",
                "icon": r["featured_icon"],
                "sort_order": r["sort_order"] or 0,
                "created_at": r["created_at"],
            }
        )
    for r in ext_featured:
        # Visa bara värdnamnet som undertext - fulla URL:en är ofta för
        # lång för att få plats i kortet. Tooltip visar full URL.
        try:
            host = urlparse(r["url"]).netloc or r["url"]
        except Exception:
            host = r["url"]
        featured.append(
            {
                "external": True,
                "href": r["url"],
                "title": r["title"],
                "subtitle": host,
                "tooltip": r["url"],
                "icon": r["icon"],
                "sort_order": r["sort_order"] or 0,
                "created_at": r["created_at"],
            }
        )
    featured.sort(key=lambda f: (f["sort_order"], f["created_at"] or ""))

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "featured": featured,
            "featured_intro_html": featured_intro_html,
            "featured_heading": featured_heading,
            "featured_subtitle": featured_subtitle,
            "senaste_nyhet": senaste_nyhet_html,
        },
    )


@router.get("/om")
async def about(request: Request):
    user = get_current_user(request)
    with get_db() as db:
        row = db.execute("SELECT value FROM site_settings WHERE key='about_content'").fetchone()
    content_html = render_markdown(row["value"] if row else "")
    return templates.TemplateResponse(
        "about.html", {"request": request, "user": user, "content": content_html}
    )


def _senaste_nyhet(md: str) -> str:
    """Första avsnittet ur nyhetstexten, för startsidan.

    Konventionen är nyast överst, så första rubriken är den senaste posten.
    Klippet går vid nästa rubrik på samma nivå - att korta på antal tecken
    hade delat en mening mitt itu, och en avhuggen nyhet läser man som ett
    fel i sidan.

    Saknas rubriker helt visas hela texten. Då är den skriven som ett stycke
    och har inga poster att välja mellan.
    """
    rader = md.strip().splitlines()
    ut: list[str] = []
    for i, rad in enumerate(rader):
        if rad.startswith("## ") and i > 0 and any(r.startswith("## ") for r in ut):
            break
        ut.append(rad)
    return "\n".join(ut).strip()


@router.get("/nyheter")
async def nyheter(request: Request):
    """Vad som ändrats i tjänsten.

    Innehållet redigeras av admin som markdown i site_settings, precis som
    om-sidan. Alternativet var en CHANGELOG-fil i repot, men då hade varje
    rad krävt en utrullning - och en rad om att något är nytt är just det
    som ska kunna skrivas när det är nytt.
    """
    user = get_current_user(request)
    with get_db() as db:
        row = db.execute("SELECT value FROM site_settings WHERE key='changelog_content'").fetchone()
    content_html = render_markdown(row["value"] if row else "")
    return templates.TemplateResponse(
        "nyheter.html", {"request": request, "user": user, "content": content_html}
    )


@router.get("/integritet")
async def integritet(request: Request):
    user = get_current_user(request)
    with get_db() as db:
        row = db.execute(
            "SELECT value FROM site_settings WHERE key='integritet_content'"
        ).fetchone()
    content_html = render_markdown(row["value"] if row else "")
    return templates.TemplateResponse(
        "integritet.html", {"request": request, "user": user, "content": content_html}
    )


def _betalning(rad: dict) -> Swishbetalning:
    """Raden som en betalning. Masken är lagrad, kryssrutorna härleds ur den."""
    mask = rad["swish_mask"] or 0
    return Swishbetalning(
        mottagare=rad["swish_mottagare"] or "",
        belopp=rad["swish_belopp"] or None,
        meddelande=rad["swish_meddelande"] or None,
        redigerbar_mottagare=bool(mask & REDIGERBAR_MOTTAGARE),
        redigerbart_belopp=bool(mask & REDIGERBART_BELOPP),
        redigerbart_meddelande=bool(mask & REDIGERBART_MEDDELANDE),
    )


def _swishsida(request: Request, rad: dict):
    """Landningssidan för en Swish-länk.

    Applänken öppnar appen förifylld på mobil, QR-koden skannas från en
    annan enhet. Båda ligger på samma sida: den som lägger ut länken vet
    inte vilket som behövs.
    """
    betalning = _betalning(rad)
    try:
        lank = applank(betalning)
    except Swishfel:
        # En rad som inte går att koda får inte fälla sidan. Koden visas
        # ändå, och den som äger länken ser felet i sin egen vy.
        lank = None
    return templates.TemplateResponse(
        "swish.html",
        {
            "request": request,
            "user": get_current_user(request),
            "code": rad["code"],
            "betalning": betalning,
            "applank": lank,
            "belopp": rad["swish_belopp"],
            "meddelande": rad["swish_meddelande"],
        },
    )


@router.get("/{code}/swish-qr.png")
async def swish_qr(code: str):
    """Swish-koden som bild. Publik, som landningssidan den sitter på.

    Egen route och inte /mina-lankar/<id>/qr.png: den senare ligger bakom
    ägarskap och bär kortlänkens adress. Den här bär betalsträngen och ska
    kunna skannas av vem som helst som står framför ett anslag.
    """
    code = code.lower()
    with get_db() as db:
        rad = db.execute(
            "SELECT * FROM links WHERE code=? AND status=? AND typ='swish'",
            (code, LinkStatus.ACTIVE),
        ).fetchone()
    if not rad:
        raise HTTPException(status_code=404)

    try:
        strang = qr_strang(_betalning(dict(rad)))
    except Swishfel:
        raise HTTPException(status_code=404) from None

    return Response(
        content=qr.png(strang, symbol_installning=qr.SWISH),
        media_type="image/png",
        headers={"Cache-Control": "public, no-cache"},
    )


@router.get("/{code}/oppna")
async def oppna_swish(request: Request, code: str):
    """Räknar trycket på Öppna Swish och skickar vidare till appen.

    Det HÄR är klicket för en Swish-länk. Sidvisningen räknas separat i
    page_views, och de två siffrorna betyder olika saker: många visningar
    och få tryck betyder att koden skannas på anslag utan att någon börjar
    betala.

    En e-postskanner som följer länken höjer siffran. Det accepteras med
    öppna ögon - page_views ger den ärliga nämnaren, och alternativet vore
    att inte kunna mäta avsikt alls.
    """
    code = code.lower()
    with get_db() as db:
        rad = db.execute(
            "SELECT * FROM links WHERE code=? AND status=? AND typ='swish'",
            (code, LinkStatus.ACTIVE),
        ).fetchone()
        if not rad:
            raise HTTPException(status_code=404)
        db.execute("INSERT INTO clicks (link_id) VALUES (?)", (rad["id"],))

    lank = applank(_betalning(dict(rad)))
    if not lank:
        # Gåva utan belopp: applänken kan inte uttrycka den. Tillbaka till
        # sidan, där QR-koden fungerar.
        return RedirectResponse(url=f"/{code}", status_code=303)
    return RedirectResponse(url=lank, status_code=303)


@router.get("/{code}")
async def redirect_code(request: Request, code: str):
    code = code.lower()  # P4.1: case-insensitive lookup
    if code in RESERVED_CODES:
        raise HTTPException(status_code=404)

    user = get_current_user(request)

    with get_db() as db:
        # Kolla bundles först
        bundle = db.execute("SELECT * FROM bundles WHERE code=? AND status=1", (code,)).fetchone()
        if bundle:
            bundle = dict(bundle)
            sections = db.execute(
                "SELECT * FROM bundle_sections WHERE bundle_id=? ORDER BY sort_order, id",
                (bundle["id"],),
            ).fetchall()
            sections = [dict(s) for s in sections]
            section_map = {s["id"]: s for s in sections}

            items = db.execute(
                "SELECT * FROM bundle_items WHERE bundle_id=? ORDER BY sort_order, id",
                (bundle["id"],),
            ).fetchall()
            items = [dict(i) for i in items]

            # Gruppera items per sektion
            grouped: dict = defaultdict(list)
            unsectioned = []
            for item in items:
                if item["section_id"] and item["section_id"] in section_map:
                    grouped[item["section_id"]].append(item)
                else:
                    unsectioned.append(item)

            theme = bundle["theme"]
            kiosk = request.query_params.get("kiosk") == "1"
            db.execute("INSERT INTO bundle_views (bundle_id) VALUES (?)", (bundle["id"],))

            body_html = render_markdown(bundle["body_md"]) if bundle.get("body_md") else None

            return templates.TemplateResponse(
                "bundle.html",
                {
                    "request": request,
                    "user": user,
                    "bundle": bundle,
                    "sections": sections,
                    "grouped": dict(grouped),
                    "unsectioned": unsectioned,
                    "theme": theme,
                    "kiosk": kiosk,
                    "base_url": BASE_URL,
                    "body_html": body_html,
                },
            )

        # Sedan kortlänkar
        row = db.execute(
            "SELECT * FROM links WHERE code=? AND status=?",
            (code, LinkStatus.ACTIVE),
        ).fetchone()

        if not row:
            return templates.TemplateResponse(
                "404.html",
                {"request": request, "code": code},
                status_code=404,
            )

        # En Swish-länk renderar en sida i stället för att omdirigera. Grenen
        # ligger EFTER uppslaget och före klickräkningen: en vanlig länk ska
        # gå exakt samma väg som förut, och sidvisningen är inte ett klick.
        if row["typ"] == "swish":
            db.execute("INSERT INTO page_views (path) VALUES (?)", (f"/{code}",))
            db.execute("UPDATE links SET last_used_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
            return _swishsida(request, dict(row))

        db.execute("INSERT INTO clicks (link_id) VALUES (?)", (row["id"],))
        db.execute("UPDATE links SET last_used_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))

    return RedirectResponse(url=row["target_url"], status_code=302)
