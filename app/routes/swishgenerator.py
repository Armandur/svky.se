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

from fastapi import APIRouter, HTTPException, Request, Response

from app import qr
from app.auth import get_current_user
from app.swish import (
    MAX_MEDDELANDE,
    Swishbetalning,
    Swishfel,
    applank,
    qr_strang,
)
from app.templating import templates

router = APIRouter()


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
        qr_strang(betalning)
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
        content=qr.png(qr_strang(betalning), symbol_installning=qr.SWISH),
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
        content=qr.svg(qr_strang(betalning), symbol_installning=qr.SWISH),
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": 'attachment; filename="swish-qr.svg"',
            "Cache-Control": "public, no-cache",
        },
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
            "kodstrang": qr_strang(betalning) if betalning else None,
            "form": dict(request.query_params),
            "max_meddelande": MAX_MEDDELANDE,
        },
    )
