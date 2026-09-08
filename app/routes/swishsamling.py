"""Publika delar av en Swish-samling: QR-bilderna och tryckräkningen.

Själva sidan renderas av catch-all i public.py, som all annan
samlingsvisning. Här ligger bara det som sidan hämtar efteråt.

Ingen inloggning, för en anslagstavla har inga inloggade besökare.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app import qr
from app.database import get_db
from app.swish import Swishfel, betalning_ur_rad, qr_strang

router = APIRouter()


def _post_i_aktiv_samling(db, item_id: int):
    """Posten, men bara om samlingen den sitter i är aktiv.

    En avaktiverad samling ska inte kunna leverera betalkoder genom att
    någon behållit adressen till bilden.
    """
    rad = db.execute(
        """SELECT i.* FROM swish_items i
             JOIN bundles b ON b.id = i.bundle_id
            WHERE i.id=? AND b.status=1 AND b.theme='swish'""",
        (item_id,),
    ).fetchone()
    if not rad:
        raise HTTPException(status_code=404)
    return rad


@router.get("/swish-post/{item_id}/qr.{andelse}")
async def post_qr(item_id: int, andelse: str):
    """Postens QR-kod som bild.

    Ritas vid varje anrop i stället för att sparas. Koden är billig att
    rita, och en sparad bild hade blivit fel i tysthet den dagen ägaren
    ändrar beloppet.
    """
    if andelse not in ("png", "svg"):
        raise HTTPException(status_code=404)

    with get_db() as db:
        rad = _post_i_aktiv_samling(db, item_id)
    try:
        strang = qr_strang(betalning_ur_rad(rad))
    except Swishfel:
        # Posten går inte att koda. Den syns inte på samlingssidan heller,
        # så adressen pekar på något som inte finns.
        raise HTTPException(status_code=404) from None

    if andelse == "png":
        return Response(
            content=qr.png(strang, symbol_installning=qr.SWISH),
            media_type="image/png",
            headers={"Cache-Control": "public, no-cache"},
        )
    return Response(
        content=qr.svg(strang, symbol_installning=qr.SWISH),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, no-cache"},
    )


@router.post("/swish-post/{item_id}/tryck")
async def rakna_tryck(request: Request, item_id: int):
    """Räkna ett tryck på Öppna Swish.

    Skickas med navigator.sendBeacon när knappen trycks, alltså INTE genom
    att leda applänken via en omdirigering här: en swish://-adress genom ett
    302-hopp är bräcklig, och betalningen är viktigare än siffran.

    Ingen CSRF-kontroll. Anropet kräver ingen inloggning, ändrar inget
    tillstånd som hör till någon användare och räknar samma sorts anonyma
    händelse som bundle_views redan gör på en GET. Vad som sparas är en
    tidsstämpel och ett post-id, inget om besökaren.

    RÄKNAR BARA TRYCK, aldrig skanningar. En QR-kod läses av Swish-appen
    utan att passera oss, så en skanning från en tryckt lapp är osynlig här.
    """
    with get_db() as db:
        _post_i_aktiv_samling(db, item_id)
        db.execute("INSERT INTO swish_taps (swish_item_id) VALUES (?)", (item_id,))

    return Response(status_code=204)
