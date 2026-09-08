"""QR-koder till kortlänkarna.

Modulen ritar koden LOKALT. Inga externa anrop, inga designkrav från tredje
part - det gäller vanliga kortlänkar. Swish-koder hämtar sitt innehåll ur en
egen spec och får en symbol i mitten, se docs/swish-qr.md och TASK-1673.
Ritvägen här är den de ska dela, men inte felkorrigeringsnivån - se nedan.

Koden bär den PUBLIKA kortlänken, aldrig target_url. Byter länken mål
fortsätter en tryckt kod att fungera, och det är hela poängen med en
kortlänk.
"""

from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass
from pathlib import Path

import qrcode
import qrcode.image.svg
from PIL import Image
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_M

from app.config import BASE_URL

# Två nivåer, av två olika skäl.
#
# Kortlänkarna får M (~15 %), standardens normalfall. H gjorde koden onödigt
# tät: en autogenererad kod (https://svky.se/ + 7 tecken) blev 29x29 moduler
# mot 25x25 med M, och en längre egen kod 33x33. Redundansen skyddade inget
# eftersom mitten är tom - den bara krympte varje modul. Mätt över hela
# spannet av kodlängder ger M 25x25 där H gav 29x29 eller 33x33.
#
# Swish-koderna får H. Där täcker symbolen mitten, och då är felkorrigeringen
# inte en marginal utan det som gör koden läsbar över huvud taget.
FELKORRIGERING_LANK = ERROR_CORRECT_M
FELKORRIGERING_SWISH = ERROR_CORRECT_H
_MODULSTORLEK = 10

# Fyra moduler är standardens minimum för den tysta zonen. En läsare behöver
# tyst yta för att hitta kanten, och en tryckt kod utan den är oläsbar hur
# skarp den än är.
MARGINAL_TRYCK = 4

_STATIC = Path(__file__).resolve().parent / "static/symboler"


@dataclass(frozen=True)
class Symbolinstallning:
    """En symbols egna regler.

    Symbolfilen ska bära sin EGEN ljusa yta mot QR-mönstret. Sköldarna gör
    det: 89 procent av pixlarna är ogenomskinliga, och den vita ytan följer
    sköldens kontur (mätt 2026-09-08). Samma sak gäller Swish-logotypen,
    vars riktlinjer dessutom förbjuder en extra bakgrund ovanpå.

    En symbol UTAN egen bakgrund behöver en vit kontrastplatta under sig,
    och den plattan måste vara helmodulsbred och centrerad över rutnätet -
    annars blir svarta pixlar kvar som en tunn ram runt den. Koden för det
    finns i slojda.de: app/services/qrkod.py, _modulanpassad_platta. Vi bär
    den inte här så länge ingen symbol behöver den.
    """

    sokvag: Path
    andel: float  # av kodens bredd
    beskrivning: str


# 30 procent är mätt, inte gissat. Marginalen mot smuts är oförändrad ända
# upp till 32 procent - koden tål lika många fläckar där som vid 24 - och
# kollapsar vid 35. Trettio ger alltså en tredjedel större sköld med kvar
# avstånd till klippkanten. Höj inte utan att mäta om.
#
# Ordningen är visningsordningen: den svarta först, för den håller koden
# enfärgad.
SYMBOLER: dict[str, Symbolinstallning] = {
    "skold-svart": Symbolinstallning(
        sokvag=_STATIC / "skold-svart.png",
        andel=0.30,
        beskrivning="Svart sköld",
    ),
    "skold-farg": Symbolinstallning(
        sokvag=_STATIC / "skold-farg.png",
        andel=0.30,
        beskrivning="Färgsköld",
    ),
}


def valj_symbol(namn: str | None) -> Symbolinstallning | None:
    """Slår upp en symbol ur ett värde som kommit utifrån.

    Namnet kommer ur en frågesträng. Det matchas mot registret och fogas
    ALDRIG in i en sökväg - ett okänt värde ger ingen symbol, inte ett fel.
    Koden ska ritas ändå.
    """
    if not namn:
        return None
    return SYMBOLER.get(namn)


def _lagg_pa_symbol(bild: Image.Image, installning: Symbolinstallning) -> Image.Image:
    """Klistrar in symbolen mitt i koden.

    Ingen premultiplicering här, till skillnad från slöjda.de. Deras
    symbolfiler bär SVART i färgkanalerna där de är genomskinliga, så LANCZOS
    blandade in svärtan i kantpixlarna och gav en mörk frans. Sköldfilerna
    bär vitt där alfa är noll (mätt 2026-09-08), så en vanlig paste med
    alfamask räcker. Byts filerna ut: mät om, och porta i så fall slöjdas
    _skala och _komponera i par - halva den lösningen ger en fel kant.
    """
    bredd = bild.width
    symbolstorlek = int(bredd * installning.andel)
    symbol = Image.open(installning.sokvag).convert("RGBA")
    symbol = symbol.resize((symbolstorlek, symbolstorlek), Image.LANCZOS)

    bild = bild.convert("RGB")
    mitt = ((bredd - symbolstorlek) // 2, (bild.height - symbolstorlek) // 2)
    bild.paste(symbol, mitt, symbol)
    return bild


def _badda_in_symbol(svgdata: bytes, kod: qrcode.QRCode, installning: Symbolinstallning) -> bytes:
    """Lägger symbolen mitt i SVG:n, i kodens egna koordinater.

    Symbolen bäddas in som en data-URI och länkas inte. Filen ska gå att
    skicka till ett tryckeri som en enda fil - en extern bildreferens blir
    ett tomt hål där.

    PNG och inte SVG, trots att vi har skölden som vektor: en SVG i en SVG
    kräver att två koordinatsystem och två stilblock slås ihop, och de två
    sköldfilernas klassnamn (.cls-1 respektive .st0) krockar med varandra.
    Källan är 1821 pixlar bred, vilket räcker för tryck.

    SvgPathImage ritar med en modul per enhet, så måtten räknas ur antalet
    moduler - inte ur pixlar, som PNG-vägen gör.
    """
    moduler = len(kod.get_matrix())
    symbolbredd = installning.andel * moduler
    bild64 = base64.b64encode(installning.sokvag.read_bytes()).decode()
    inre_mitt = (moduler - symbolbredd) / 2
    lager = (
        f'<image x="{inre_mitt:.3f}" y="{inre_mitt:.3f}" '
        f'width="{symbolbredd:.3f}" height="{symbolbredd:.3f}" '
        f'href="data:image/png;base64,{bild64}"/>'
    )
    return re.sub(rb"</svg>\s*$", lager.encode() + b"</svg>", svgdata)


def _felkorrigering(installning: Symbolinstallning | None) -> int:
    """H när en symbol täcker mitten, annars M.

    Nivån måste väljas INNAN matrisen ritas. En sköld klistrad på en M-kod
    ser perfekt ut och går inte att läsa av.
    """
    return FELKORRIGERING_SWISH if installning else FELKORRIGERING_LANK


def lankadress(code: str) -> str:
    """Den publika adressen koden ska bära."""
    return f"{BASE_URL.rstrip('/')}/{code}"


def _kod(data: str, marginal: int, felkorrigering: int = FELKORRIGERING_LANK) -> qrcode.QRCode:
    kod = qrcode.QRCode(
        error_correction=felkorrigering,
        border=marginal,
        box_size=_MODULSTORLEK,
    )
    kod.add_data(data)
    kod.make(fit=True)
    return kod


def png(data: str, marginal: int = MARGINAL_TRYCK, symbol: str | None = None) -> bytes:
    """QR-koden som PNG. Vit bakgrund, svart mönster.

    Med en symbol ritas matrisen tätare, se _felkorrigering.
    """
    installning = valj_symbol(symbol)
    bild = _kod(data, marginal, _felkorrigering(installning)).make_image(
        fill_color="black", back_color="white"
    )
    bild = bild.convert("RGB")
    if installning:
        bild = _lagg_pa_symbol(bild, installning)
    buffert = io.BytesIO()
    bild.save(buffert, format="PNG")
    return buffert.getvalue()


def svg(data: str, marginal: int = MARGINAL_TRYCK, symbol: str | None = None) -> bytes:
    """QR-koden som SVG, för tryck. Skalbar utan hackiga kanter.

    SvgPathImage ritar BARA den svarta banan - filen blir genomskinlig. På
    vitt papper syns det inte, men lagd på färgat underlag eller en mörk sida
    inverteras koden och blir oläsbar. Vi lägger därför in en vit rektangel
    under banan. Slöjda har inte gjort det, se docs/swish-qr.md.
    """
    installning = valj_symbol(symbol)
    kod = _kod(data, marginal, _felkorrigering(installning))
    buffert = io.BytesIO()
    kod.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(buffert)
    ut = buffert.getvalue()

    # SvgPathImage ritar i millimeter med en modul per enhet, så måtten
    # räknas ur antalet moduler och inte ur pixlar.
    moduler = len(kod.get_matrix())
    bakgrund = (f'<rect x="0" y="0" width="{moduler}" height="{moduler}" fill="#ffffff"/>').encode()
    ut = re.sub(rb"(<path)", bakgrund + rb"\1", ut, count=1)
    if installning:
        ut = _badda_in_symbol(ut, kod, installning)
    return ut


def filnamn(code: str, andelse: str, symbol: str | None = None) -> str:
    """Namn som går att skilja åt i nedladdningsmappen.

    Den som laddar ner koder inför tryck hämtar flera i följd, och
    'qrcode.svg (3)' säger ingenting en vecka senare. Symbolen ingår i
    namnet av samma skäl: ett paket med sex koder behöver sex olika namn.
    """
    trygg = re.sub(r"[^A-Za-z0-9_-]", "", code) or "kortlank"
    if symbol and symbol in SYMBOLER:
        return f"svky-{trygg}-{symbol}.{andelse}"
    return f"svky-{trygg}.{andelse}"
