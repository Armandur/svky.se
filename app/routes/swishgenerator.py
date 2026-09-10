"""Generatorn för Swish-koder på /swish och /swishqr.

Ett VERKTYG, inte en länk. Ingenting sparas: koderna räknas fram ur
frågesträngen vid varje anrop, och den som stänger fliken har inget kvar
utom det hen laddat ner. Det är avsikten - en Swish-kod är en betalning som
ska tryckas på en lapp, inte en adress som ska leva vidare i en databas.

Två adresser, samma sida. /swish och /swishqr står båda i RESERVED_CODES och
folk skriver rimligen det ena eller det andra.

Ingen inloggning. Verktyget rör ingen data och pekar ut ett Swish-nummer som
den som fyller i redan känner till.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app import qr
from app.auth import get_current_user
from app.swish import (
    MAX_MEDDELANDE,
    Swishbetalning,
    Swishfel,
    applank,
    qr_strang,
    url_strang,
)
from app.swishtext import lastext
from app.templating import templates

router = APIRouter()

_KODFORMAT = {"c": qr_strang, "url": url_strang}


def _valj_format(varde: str | None) -> str:
    """Ett känt format, med C-formatet som säkert förval."""
    return varde if varde in _KODFORMAT else "c"


def _format_ur_fragan(request: Request) -> str:
    return _valj_format(request.query_params.get("format"))


def _kodstrang(betalning: Swishbetalning, kodformat: str) -> str:
    return _KODFORMAT[kodformat](betalning)


def _kodfraga(request: Request) -> str:
    """Känd och URL-kodad delmängd för bild- och nedladdningsadresser."""
    fraga = request.query_params
    parametrar = []
    for namn in ("mottagare", "belopp", "meddelande"):
        if fraga.get(namn):
            parametrar.append((namn, fraga[namn]))
    for namn in ("fri_mottagare", "fritt_belopp", "fritt_meddelande"):
        if fraga.get(namn) == "1":
            parametrar.append((namn, "1"))
    parametrar.append(("format", _format_ur_fragan(request)))
    return urlencode(parametrar)


def _ur_fragan(request: Request) -> tuple[Swishbetalning | None, str | None]:
    """Betalningen ur frågesträngen, eller (None, fel).

    Formuläret postar inte. Allt ligger i adressen, så en ifylld generator
    går att spara som bokmärke, mejla till en kollega eller klistra in i ett
    ärende. Det är billigare än att spara utkast åt någon.
    """
    fraga = request.query_params
    if not fraga.get("mottagare"):
        return None, None

    betalning = Swishbetalning(
        mottagare=fraga.get("mottagare", ""),
        belopp=(fraga.get("belopp") or "").strip() or None,
        meddelande=(fraga.get("meddelande") or "").strip() or None,
        redigerbar_mottagare=fraga.get("fri_mottagare") == "1",
        redigerbart_belopp=fraga.get("fritt_belopp") == "1",
        redigerbart_meddelande=fraga.get("fritt_meddelande") == "1",
    )
    try:
        _kodstrang(betalning, _format_ur_fragan(request))
    except Swishfel as fel:
        return None, str(fel)
    return betalning, None


@router.get("/swish-kod.png")
async def swish_kod_png(request: Request):
    """Koden som bild, ritad ur frågesträngen.

    Egen adress så att bilden går att spara med högerklick och länka till
    från sidan. Ingen cache-huvud som binder: byter någon ett tecken i
    frågan är det en annan bild.
    """
    betalning, fel = _ur_fragan(request)
    if betalning is None:
        raise HTTPException(status_code=404, detail=fel or "Ofullständig betalning")

    return Response(
        content=qr.png(
            _kodstrang(betalning, _format_ur_fragan(request)), symbol_installning=qr.SWISH
        ),
        media_type="image/png",
        headers={
            "Content-Disposition": 'attachment; filename="swish-qr.png"',
            "Cache-Control": "public, no-cache",
        },
    )


@router.get("/swish-kod.svg")
async def swish_kod_svg(request: Request):
    """Koden som SVG, för tryck. Skalbar utan hackiga kanter."""
    betalning, fel = _ur_fragan(request)
    if betalning is None:
        raise HTTPException(status_code=404, detail=fel or "Ofullständig betalning")

    return Response(
        content=qr.svg(
            _kodstrang(betalning, _format_ur_fragan(request)), symbol_installning=qr.SWISH
        ),
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": 'attachment; filename="swish-qr.svg"',
            "Cache-Control": "public, no-cache",
        },
    )


@router.get("/swish-data")
async def swish_data(request: Request):
    """Betalningen som JSON, för generatorn som räknar om medan man skriver.

    Samma frågesträng som sidan själv, samma _ur_fragan() under. Sidan får
    aldrig räkna fram en kodsträng i webbläsaren: gör den det finns formatet
    på två ställen, och den dagen app/swish.py rättas glider de isär.

    `lage` säger vad panelen ska visa. "tom" är inte ett fel - det är en
    halvifylld blankett, och den ska inte skälla på någon som skriver.

    Ett halvskrivet Swish-nummer är därför alltid "tom", aldrig "fel". Utan
    den regeln möts den som skrivit sin första siffra av ett felmeddelande
    om beloppet, eftersom kontrollen av beloppet ligger före rensningen av
    numret. Fler än tio siffror är däremot ett riktigt fel: då har man
    skrivit färdigt och skrivit fel.
    """
    siffror = "".join(t for t in request.query_params.get("mottagare", "") if t.isdigit())
    if len(siffror) < 10:
        return JSONResponse({"lage": "tom", "fel": None, "kodstrang": None, "applank": None})

    betalning, fel = _ur_fragan(request)
    if betalning is None:
        return JSONResponse(
            {"lage": "fel" if fel else "tom", "fel": fel, "kodstrang": None, "applank": None}
        )

    return JSONResponse(
        {
            "lage": "ok",
            "fel": None,
            "kodstrang": _kodstrang(betalning, _format_ur_fragan(request)),
            "applank": applank(betalning),
            "mottagare": betalning.mottagare,
            "lastext": lastext(betalning, _format_ur_fragan(request)),
        }
    )


@router.get("/swish")
@router.get("/swishqr")
async def generator(request: Request):
    betalning, fel = _ur_fragan(request)

    return templates.TemplateResponse(
        "swish_generator.html",
        {
            "request": request,
            "user": get_current_user(request),
            "betalning": betalning,
            "fel": fel,
            "applank": applank(betalning) if betalning else None,
            "kodstrang": _kodstrang(betalning, _format_ur_fragan(request)) if betalning else None,
            "lastext": lastext(betalning, _format_ur_fragan(request)) if betalning else None,
            "form": dict(request.query_params),
            "kodformat": _format_ur_fragan(request),
            "kodfraga": _kodfraga(request),
            "max_meddelande": MAX_MEDDELANDE,
        },
    )
