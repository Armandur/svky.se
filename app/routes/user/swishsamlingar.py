"""Swishposterna i en samling med theme='swish'.

Samlingen SJÄLV är en vanlig bundle: kortkod, ägare, status och överlåtelse
kommer därifrån oförändrade. Bara posterna bor här, i tabellen swish_items,
för en swishpost bär mottagare, belopp, meddelande och låsmask medan
bundle_items bär title och url.

Delas upp från bundles.py som redan är över tusen rader. Ägarvyn renderas
härifrån via samlingsvy(), som bundles.min_samling grenar av till när temat
är swish.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app import qr
from app.config import BASE_URL
from app.csrf import get_csrf_secret, validate_csrf_token
from app.database import get_db
from app.deps import get_user_or_redirect
from app.swish import (
    MAX_MEDDELANDE,
    Swishbetalning,
    Swishfel,
    applank,
    betalning_ur_rad,
    qr_strang,
)
from app.swishtext import lastext
from app.templating import templates
from app.validation import MAX_NAME_LENGTH, MAX_TEXT_LENGTH, validate_length

router = APIRouter()

SWISHTEMA = "swish"


def _egen_samling(db, bundle_id: int, user_id: int):
    """Samlingen om den är användarens och faktiskt är en swishsamling."""
    rad = db.execute(
        "SELECT * FROM bundles WHERE id=? AND owner_id=? AND theme=?",
        (bundle_id, user_id, SWISHTEMA),
    ).fetchone()
    if not rad:
        raise HTTPException(status_code=404)
    return dict(rad)


def _poster(db, bundle_id: int) -> list[dict]:
    """Posterna med sina två strängar uträknade.

    Strängarna sparas aldrig. De räknas fram ur fälten vid varje visning, så
    en rättning i app/swish.py slår igenom på gamla poster utan migration.
    """
    rader = db.execute(
        "SELECT * FROM swish_items WHERE bundle_id=? ORDER BY sort_order, id",
        (bundle_id,),
    ).fetchall()
    ut = []
    for rad in rader:
        post = dict(rad)
        betalning = betalning_ur_rad(rad)
        try:
            post["kodstrang"] = qr_strang(betalning)
            post["applank"] = applank(betalning)
            post["fel"] = None
            post["lastext"] = lastext(betalning)
        except Swishfel as fel:
            # Allt som skrivs härifrån går genom _falt() och är kodbart. En
            # rad som ändrats direkt i databasen behöver ändå kunna visas:
            # ÄGAREN ska se vilken post som är trasig och kunna rätta den,
            # inte mötas av en tom sida där hela samlingen låg.
            post["kodstrang"] = None
            post["applank"] = None
            post["fel"] = str(fel)
            post["lastext"] = None
        # Sant betyder att den som öppnar applänken kan peka om betalningen
        # till ett annat nummer. Se applank(). Visas bara för ÄGAREN.
        post["mottagare_gar_att_andra"] = betalning.mask() != 0
        ut.append(post)
    return ut


def _falt(
    mottagare: str,
    belopp: str,
    meddelande: str,
    fri_mottagare: bool,
    fritt_belopp: bool,
    fritt_meddelande: bool,
) -> tuple[Swishbetalning, str | None]:
    """Formulärets fält som betalning, eller (betalning, felmeddelande).

    Kontrollen görs genom att faktiskt koda strängen. Då kan validering och
    kodning inte glida isär: det som går att spara är det som går att rita.
    """
    betalning = Swishbetalning(
        mottagare=mottagare,
        belopp=belopp.strip() or None,
        meddelande=meddelande.strip() or None,
        redigerbar_mottagare=fri_mottagare,
        redigerbart_belopp=fritt_belopp,
        redigerbart_meddelande=fritt_meddelande,
    )
    try:
        qr_strang(betalning)
    except Swishfel as fel:
        return betalning, str(fel)

    return betalning.normaliserad(), None


def _tillbaka(
    bundle_id: int, fel: str | None = None, item_id: int | None = None
) -> RedirectResponse:
    """Tillbaka till samlingen, med felet knutet till rätt formulär.

    `item_id` säger VILKEN post felet gäller, så mallen kan visa det där i
    stället för som en banner högst upp. Utan det hamnar felet i formuläret
    för en ny kod, som är där det kommer ifrån när ingen post är utpekad.

    Den här vägen används bara utan JavaScript. Med skript prövas
    betalningen mot /swish-data medan man skriver, och knappen släpper
    aldrig igenom något som ändå skulle avvisas här.
    """
    adress = f"/mina-samlingar/{bundle_id}"
    if fel:
        import urllib.parse

        adress += f"?swish_error={urllib.parse.quote(fel)}"
        if item_id is not None:
            adress += f"&fel_post={item_id}"
    else:
        adress += "?saved=1"
    return RedirectResponse(url=adress, status_code=303)


async def samlingsvy(request: Request, user: dict, bundle: dict):
    """Ägarens redigeringsvy. Anropas från bundles.min_samling."""
    with get_db() as db:
        poster = _poster(db, bundle["id"])
        tryck = {
            rad["swish_item_id"]: rad["antal"]
            for rad in db.execute(
                """SELECT t.swish_item_id, COUNT(*) AS antal
                     FROM swish_taps t
                     JOIN swish_items i ON i.id = t.swish_item_id
                    WHERE i.bundle_id=?
                 GROUP BY t.swish_item_id""",
                (bundle["id"],),
            ).fetchall()
        }
    for post in poster:
        post["tryck"] = tryck.get(post["id"], 0)

    return templates.TemplateResponse(
        "mina_swishsamlingar_detalj.html",
        {
            "request": request,
            "user": user,
            "bundle": bundle,
            "poster": poster,
            "base_url": BASE_URL,
            "max_meddelande": MAX_MEDDELANDE,
            "saved": request.query_params.get("saved") == "1",
            "swish_error": request.query_params.get("swish_error"),
            "fel_post": request.query_params.get("fel_post"),
        },
    )


@router.post("/mina-samlingar/{bundle_id}/swish-poster")
async def lagg_till_post(
    request: Request,
    bundle_id: int,
    title: str = Form(...),
    description: str = Form(""),
    mottagare: str = Form(...),
    belopp: str = Form(""),
    meddelande: str = Form(""),
    fri_mottagare: str = Form(""),
    fritt_belopp: str = Form(""),
    fritt_meddelande: str = Form(""),
    csrf_token: str = Form(...),
):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    user = get_user_or_redirect(request)

    title = title.strip()
    if not title:
        return _tillbaka(bundle_id, "Swish-koden behöver en rubrik.")
    if fel := validate_length(title, MAX_NAME_LENGTH, "Namnet"):
        return _tillbaka(bundle_id, fel)
    if fel := validate_length(description, MAX_TEXT_LENGTH, "Beskrivningen"):
        return _tillbaka(bundle_id, fel)

    betalning, fel = _falt(
        mottagare,
        belopp,
        meddelande,
        fri_mottagare == "1",
        fritt_belopp == "1",
        fritt_meddelande == "1",
    )
    if fel:
        return _tillbaka(bundle_id, fel)

    with get_db() as db:
        _egen_samling(db, bundle_id, user["id"])
        nasta = db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM swish_items WHERE bundle_id=?",
            (bundle_id,),
        ).fetchone()["n"]
        db.execute(
            """INSERT INTO swish_items
               (bundle_id, title, description, mottagare, belopp, meddelande,
                fri_mottagare, fritt_belopp, fritt_meddelande, sort_order)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                bundle_id,
                title,
                description.strip() or None,
                betalning.mottagare,
                betalning.belopp,
                betalning.meddelande,
                int(betalning.redigerbar_mottagare),
                int(betalning.redigerbart_belopp),
                int(betalning.redigerbart_meddelande),
                nasta,
            ),
        )
        db.execute("UPDATE bundles SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (bundle_id,))

    return _tillbaka(bundle_id)


@router.post("/mina-samlingar/{bundle_id}/swish-poster/{item_id}/update")
async def uppdatera_post(
    request: Request,
    bundle_id: int,
    item_id: int,
    title: str = Form(...),
    description: str = Form(""),
    mottagare: str = Form(...),
    belopp: str = Form(""),
    meddelande: str = Form(""),
    fri_mottagare: str = Form(""),
    fritt_belopp: str = Form(""),
    fritt_meddelande: str = Form(""),
    csrf_token: str = Form(...),
):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    user = get_user_or_redirect(request)

    title = title.strip()
    if not title:
        return _tillbaka(bundle_id, item_id=item_id, fel="Swish-koden behöver en rubrik.")
    if fel := validate_length(title, MAX_NAME_LENGTH, "Namnet"):
        return _tillbaka(bundle_id, item_id=item_id, fel=fel)
    if fel := validate_length(description, MAX_TEXT_LENGTH, "Beskrivningen"):
        return _tillbaka(bundle_id, item_id=item_id, fel=fel)

    betalning, fel = _falt(
        mottagare,
        belopp,
        meddelande,
        fri_mottagare == "1",
        fritt_belopp == "1",
        fritt_meddelande == "1",
    )
    if fel:
        return _tillbaka(bundle_id, item_id=item_id, fel=fel)

    with get_db() as db:
        _egen_samling(db, bundle_id, user["id"])
        andrade = db.execute(
            """UPDATE swish_items SET title=?, description=?, mottagare=?, belopp=?,
                      meddelande=?, fri_mottagare=?, fritt_belopp=?, fritt_meddelande=?
                WHERE id=? AND bundle_id=?""",
            (
                title,
                description.strip() or None,
                betalning.mottagare,
                betalning.belopp,
                betalning.meddelande,
                int(betalning.redigerbar_mottagare),
                int(betalning.redigerbart_belopp),
                int(betalning.redigerbart_meddelande),
                item_id,
                bundle_id,
            ),
        ).rowcount
        if not andrade:
            raise HTTPException(status_code=404)
        db.execute("UPDATE bundles SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (bundle_id,))

    return _tillbaka(bundle_id)


@router.post("/mina-samlingar/{bundle_id}/swish-poster/{item_id}/delete")
async def ta_bort_post(request: Request, bundle_id: int, item_id: int, csrf_token: str = Form(...)):
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    user = get_user_or_redirect(request)

    with get_db() as db:
        _egen_samling(db, bundle_id, user["id"])
        # Trycken går först, uttryckligen. ON DELETE CASCADE på swish_taps
        # sköter det redan, men en radering som lämnar räknare kvar är ett
        # dyrt fel att upptäcka sent.
        db.execute(
            "DELETE FROM swish_taps WHERE swish_item_id IN "
            "(SELECT id FROM swish_items WHERE id=? AND bundle_id=?)",
            (item_id, bundle_id),
        )
        db.execute("DELETE FROM swish_items WHERE id=? AND bundle_id=?", (item_id, bundle_id))

    return _tillbaka(bundle_id)


@router.post("/mina-samlingar/{bundle_id}/swish-poster/{item_id}/move")
async def flytta_post(
    request: Request,
    bundle_id: int,
    item_id: int,
    riktning: str = Form(...),
    csrf_token: str = Form(...),
):
    """Byt plats med posten ovanför eller nedanför.

    Ordningen syns på en tryckt lapp, så den ska gå att styra. Två knappar
    räcker: en samling har tre poster, inte trettio.
    """
    if not validate_csrf_token(csrf_token, get_csrf_secret(request)):
        raise HTTPException(status_code=403)
    user = get_user_or_redirect(request)

    with get_db() as db:
        _egen_samling(db, bundle_id, user["id"])
        rader = [
            dict(r)
            for r in db.execute(
                "SELECT id FROM swish_items WHERE bundle_id=? ORDER BY sort_order, id",
                (bundle_id,),
            ).fetchall()
        ]
        idn = [r["id"] for r in rader]
        if item_id not in idn:
            raise HTTPException(status_code=404)
        i = idn.index(item_id)
        j = i - 1 if riktning == "upp" else i + 1
        if 0 <= j < len(idn):
            idn[i], idn[j] = idn[j], idn[i]
            for plats, ident in enumerate(idn, start=1):
                db.execute("UPDATE swish_items SET sort_order=? WHERE id=?", (plats, ident))

    return RedirectResponse(url=f"/mina-samlingar/{bundle_id}", status_code=303)


@router.get("/mina-samlingar/{bundle_id}/swish-poster/{item_id}/qr.{andelse}")
async def post_qr(request: Request, bundle_id: int, item_id: int, andelse: str):
    """Postens egen QR-kod, för den som vill trycka just den betalningen.

    Samlingens kod finns redan via bundles egen QR-route. Den här ger den
    enskilda betalningen, alltså samma bild som generatorn hade gett.
    """
    user = get_user_or_redirect(request)
    if andelse not in ("png", "svg"):
        raise HTTPException(status_code=404)

    with get_db() as db:
        _egen_samling(db, bundle_id, user["id"])
        rad = db.execute(
            "SELECT * FROM swish_items WHERE id=? AND bundle_id=?", (item_id, bundle_id)
        ).fetchone()
        if not rad:
            raise HTTPException(status_code=404)
        strang = qr_strang(betalning_ur_rad(rad))

    if andelse == "png":
        return Response(
            content=qr.png(strang, symbol_installning=qr.SWISH),
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="swish-{item_id}.png"'},
        )
    return Response(
        content=qr.svg(strang, symbol_installning=qr.SWISH),
        media_type="image/svg+xml",
        headers={"Content-Disposition": f'attachment; filename="swish-{item_id}.svg"'},
    )
