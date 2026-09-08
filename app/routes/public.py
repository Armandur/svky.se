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

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.auth import get_current_user
from app.config import BASE_URL, RESERVED_CODES, LinkStatus
from app.database import get_db
from app.markdown_safe import render_markdown
from app.swish import Swishfel, applank, betalning_ur_rad, qr_strang
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

            # Swishsamlingen har egen sida: betalkoder i stället för länkar,
            # och ingen sektionsindelning. Vyn ligger före den vanliga för
            # att slippa hämta sektioner och items som inte finns.
            if bundle["theme"] == "swish":
                poster = [
                    dict(r)
                    for r in db.execute(
                        "SELECT * FROM swish_items WHERE bundle_id=? ORDER BY sort_order, id",
                        (bundle["id"],),
                    ).fetchall()
                ]
                visbara = []
                for post in poster:
                    betalning = betalning_ur_rad(post)
                    try:
                        post["kodstrang"] = qr_strang(betalning)
                        post["applank"] = applank(betalning)
                    except Swishfel:
                        # En post som inte går att koda utelämnas här. Ett
                        # kort som saknas är bättre än en anslagstavla som
                        # pekar på en tom sida - och ägaren ser felet i sin
                        # egen vy. Allt som skapas via gränssnittet är
                        # kodbart, så det här är en rad någon ändrat i
                        # databasen.
                        continue
                    visbara.append(post)
                poster = visbara
                db.execute("INSERT INTO bundle_views (bundle_id) VALUES (?)", (bundle["id"],))
                return templates.TemplateResponse(
                    "swish_bundle.html",
                    {
                        "request": request,
                        "user": user,
                        "bundle": bundle,
                        "poster": poster,
                        "base_url": BASE_URL,
                        "body_html": (
                            render_markdown(bundle["body_md"]) if bundle.get("body_md") else None
                        ),
                    },
                )
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
            "SELECT id, target_url FROM links WHERE code=? AND status=?",
            (code, LinkStatus.ACTIVE),
        ).fetchone()

        if not row:
            return templates.TemplateResponse(
                "404.html",
                {"request": request, "code": code},
                status_code=404,
            )

        db.execute("INSERT INTO clicks (link_id) VALUES (?)", (row["id"],))
        db.execute("UPDATE links SET last_used_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))

    return RedirectResponse(url=row["target_url"], status_code=302)
