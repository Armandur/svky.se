"""Gravplatslänkar: landningssida och nodsidor (TASK-2145).

Adressen `/10/had/hkn/allm/0446` läses i tre steg:

1. Hela sökvägen slås upp mot gravplatsernas frusna sökvägar och alias.
2. Annars vandrar vi ner i nodträdet så långt segmenten räcker.
3. Är exakt ett segment kvar under ett kvarter är sökvägen välformad men
   oregistrerad, och besökaren får platsen och kontaktuppgifterna ändå.

Ingen omdirigering. Ingen leverantör har permalänk per gravplats, och
sökningen kan ge noll eller flera träffar - då är en sida med en söklänk
ärligare än en 302 som ibland landar rätt.

Sidan visar platsen, aldrig personen. Ingen persondata passerar den här
modulen, och visningsräknaren bär bara tidsstämpel och gravplats-id.
"""

from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request

from app import gravplats
from app.config import STIFT
from app.database import get_db
from app.templating import templates

router = APIRouter()

# Nivåer som får bära gravplatser. En sökväg med ett okänt segment under en
# kyrkogård är inte välformad - då saknas kvarteret, och sidan hade lovat en
# plats den inte kan peka ut.
BARANDE_NIVAER = ("kvarter", "avdelning")


def _svar(mall: str, kontext: dict, status: int = 200):
    """Renderar en gravplatssida med noindex satt på två sätt.

    Metataggen räcker för sökmotorer som hämtar sidan. Huvudet gäller även
    när adressen delas vidare som en resurs - och den här sidan ska aldrig
    hamna i ett sökresultat, hur den än nås.
    """
    svar = templates.TemplateResponse(mall, kontext, status_code=status)
    svar.headers["X-Robots-Tag"] = "noindex, nofollow"
    return svar


def _leverantor(sokmall: str | None) -> str:
    """Namnet besökaren känner igen, läst ur söklänkens värdnamn.

    Som härledning och inte som eget fält: det är samma uppgift två gånger,
    och den dag en förvaltning byter system är söklänken ändå det som måste
    ändras.
    """
    if not sokmall:
        return "leverantören"
    vard = urlparse(sokmall).netloc.lower().removeprefix("www.")
    return {"svenskagravar.se": "Svenskagravar", "gravar.se": "Gravar.se"}.get(vard, vard)


def _gemensamt(request: Request, kedja: list) -> dict:
    smulor = []
    vag = ""
    for nod in kedja:
        vag = f"{vag}/{nod['segment']}"
        smulor.append({"namn": gravplats.etikett(nod), "sokvag": vag, "niva": nod["niva"]})
    arvda = gravplats.arvda(kedja)
    forvaltning = next((n for n in kedja if n["niva"] == "forvaltning"), None)
    return {
        "request": request,
        "utatpekande": True,
        "kedja": kedja,
        "tema": gravplats.tema_av(kedja),
        "arvda": arvda,
        "smulor": smulor,
        "forvaltning": gravplats.etikett(forvaltning) if forvaltning else None,
        "leverantor": _leverantor(arvda["sokmall"]),
        # Platsen läses som en rad: kyrkogården vid namn, kvarteret vid kod.
        "plats": ", ".join(
            gravplats.etikett(n)
            for n in kedja
            if n["niva"] in ("kyrkogard", "kvarter", "avdelning")
        ),
    }


async def visa_sokvag(request: Request):
    segment = gravplats.dela_sokvag(request.url.path)
    if len(segment) < 2:
        raise HTTPException(status_code=404)

    with get_db() as db:
        rad = gravplats.hamta_gravplats(db, gravplats.sokvag_av(segment))
        if rad:
            kedja = gravplats.kedja_till(db, rad["nod_id"])
            db.execute("INSERT INTO gravplats_views (gravplats_id) VALUES (?)", (rad["id"],))
            kontext = _gemensamt(request, kedja)
            kontext.update(
                {
                    "nummer": rad["nummer"],
                    "beteckning": gravplats.fullt_nummer(kedja, rad["nummer"]),
                    "sok_url": gravplats.sok_url(kedja, rad["nummer"]),
                    "kart_url": gravplats.kart_url(kedja, rad["nummer"]),
                    "registrerad": True,
                }
            )
            return _svar("gravplats.html", kontext)

        kedja, kvar = gravplats.vandra(db, segment)

        if not kvar:
            noden = kedja[-1]
            kontext = _gemensamt(request, kedja)
            kontext.update(
                {
                    "nod": noden,
                    "nodnamn": gravplats.etikett(noden),
                    "barn": [
                        {"namn": gravplats.etikett(b), "segment": b["segment"]}
                        for b in gravplats.barn(db, noden["id"])
                    ],
                }
            )
            return _svar("gravnod.html", kontext)

        # Ett okänt segment under ett kvarter: skylten finns, raden saknas.
        # Besökaren står vid graven med telefonen i handen, så sidan svarar
        # 200 och visar vem som kan svara. En 404 hade gett en felruta i
        # stället - och statuskoden säger ingen människa någonting här.
        if len(kvar) == 1 and kedja and kedja[-1]["niva"] in BARANDE_NIVAER:
            kontext = _gemensamt(request, kedja)
            kontext.update(
                {
                    "nummer": kvar[0],
                    "beteckning": gravplats.fullt_nummer(kedja, kvar[0]),
                    # Ingen förifylld söklänk här. Segmentet är vår slug, inte
                    # gravplatsnumret: `0009/17` slugas till `0009-17` och
                    # `P.11` till `p-11`. En sökning på slugen ger noll
                    # träffar hos leverantören, och en tom träfflista läses
                    # som att graven inte finns. Kontaktkortet får bära det.
                    "sok_url": None,
                    "kart_url": None,
                    "registrerad": False,
                }
            )
            return _svar("gravplats.html", kontext)

    raise HTTPException(status_code=404)


# En route per stiftskod i stället för ett girigt /{stift}/{resten:path}.
# Den giriga formen hade kört handlern även för adresser som inte är
# gravplatssökvägar och därmed svalt allt som monteras efter - ordningen i
# main.py hade blivit det enda som höll isär dem.
for _kod in sorted(STIFT):
    router.add_api_route(
        f"/{_kod}/{{resten:path}}",
        visa_sokvag,
        methods=["GET"],
        include_in_schema=False,
        name=f"gravsokvag_{_kod}",
    )
