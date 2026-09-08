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
from PIL import Image, ImageChops
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


# Swish-symbolen ligger UTANFÖR SYMBOLER med flit. Den hör till en
# Swish-betalkod och ska inte gå att välja för en vanlig kortlänk, varken i
# växeln eller genom en frågesträng.
#
# 25 procent är Swish eget krav, inte vårt val som sköldarnas 30. Andelen
# räknas mot koden UTAN marginal - Swish säger inte om den tysta zonen ingår,
# och räknat på hela bilden blir symbolen 31 procent av själva koden, vilket
# ligger nära vad felkorrigering H klarar.
SWISH = Symbolinstallning(
    sokvag=_STATIC / "swish.png",
    andel=0.25,
    beskrivning="Swish",
)


def valj_symbol(namn: str | None) -> Symbolinstallning | None:
    """Slår upp en symbol ur ett värde som kommit utifrån.

    Namnet kommer ur en frågesträng. Det matchas mot registret och fogas
    ALDRIG in i en sökväg - ett okänt värde ger ingen symbol, inte ett fel.
    Koden ska ritas ändå.
    """
    if not namn:
        return None
    return SYMBOLER.get(namn)


def _skala(symbol: Image.Image, storlek: int) -> Image.Image:
    """Skalar symbolen utan att kanterna smutsas ner.

    PNG-filer bär ofta ett värde i färgkanalerna där de är helt genomskinliga,
    eftersom värdet ändå inte syns. Swish-symbolen bär SVART där (mätt
    2026-09-08), och LANCZOS interpolerar färg och alfa var för sig - så en
    rak resize blandar in svärtan i kantpixlarna och ger en mörk frans runt
    symbolen.

    Botemedlet är att multiplicera färgen med alfa FÖRE skalningen. Då bidrar
    en genomskinlig pixel med noll i stället för med sin dolda färg. Bilden
    lämnas premultiplicerad, och _komponera räknar med just den formen.

    Sköldarna bär vitt under alfa 0 och klarar sig utan det här steget, men
    behandlingen är rätt för dem också: den ger samma resultat och en fil
    mindre att hålla reda på.
    """
    r, g, b, a = symbol.split()
    farg = Image.merge(
        "RGB",
        (
            ImageChops.multiply(r, a),
            ImageChops.multiply(g, a),
            ImageChops.multiply(b, a),
        ),
    ).resize((storlek, storlek), Image.LANCZOS)
    return Image.merge("RGBA", (*farg.split(), a.resize((storlek, storlek), Image.LANCZOS)))


def _komponera(under: Image.Image, over: Image.Image, position: tuple[int, int]) -> None:
    """Lägger en premultiplicerad bild på `under`, på plats.

    En vanlig paste med alfamask förutsätter att färgen INTE är
    premultiplicerad och räknar då in alfa två gånger - resultatet blir för
    mörkt. Kompositeringen görs därför för hand: under * (1 - alfa) + färg.
    """
    x, y = position
    yta = under.crop((x, y, x + over.width, y + over.height)).convert("RGB")
    farg = over.convert("RGB")
    invers = ImageChops.invert(over.split()[3])
    kvar = Image.merge("RGB", tuple(ImageChops.multiply(kanal, invers) for kanal in yta.split()))
    under.paste(ImageChops.add(kvar, farg), (x, y))


def _lagg_pa_symbol(bild: Image.Image, installning: Symbolinstallning) -> Image.Image:
    """Klistrar in symbolen mitt i koden.

    Ingen vit platta bakom. Symbolfilerna bär sin egen ljusa yta - sköldarna
    hela vägen ut till konturen, Swish-logotypen som en rund bakgrund med
    genomskinliga hörn. Swish riktlinjer förbjuder dessutom uttryckligen en
    extra bakgrund ovanpå deras.
    """
    bredd = bild.width
    symbolstorlek = int(bredd * installning.andel)
    symbol = _skala(Image.open(installning.sokvag).convert("RGBA"), symbolstorlek)

    bild = bild.convert("RGB")
    mitt = ((bredd - symbolstorlek) // 2, (bild.height - symbolstorlek) // 2)
    _komponera(bild, symbol, mitt)
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


def png(
    data: str,
    marginal: int = MARGINAL_TRYCK,
    symbol: str | None = None,
    symbol_installning: Symbolinstallning | None = None,
) -> bytes:
    """QR-koden som PNG. Vit bakgrund, svart mönster.

    Med en symbol ritas matrisen tätare, se _felkorrigering.

    `symbol` slås upp i SYMBOLER och kommer från en frågesträng.
    `symbol_installning` går förbi det uppslaget och används för symboler som
    INTE ska vara valbara utifrån - Swish-logotypen hör till en betalkod och
    ska aldrig kunna hamna på en vanlig kortlänk.
    """
    installning = symbol_installning or valj_symbol(symbol)
    bild = _kod(data, marginal, _felkorrigering(installning)).make_image(
        fill_color="black", back_color="white"
    )
    bild = bild.convert("RGB")
    if installning:
        bild = _lagg_pa_symbol(bild, installning)
    buffert = io.BytesIO()
    bild.save(buffert, format="PNG")
    return buffert.getvalue()


def svg(
    data: str,
    marginal: int = MARGINAL_TRYCK,
    symbol: str | None = None,
    symbol_installning: Symbolinstallning | None = None,
) -> bytes:
    """QR-koden som SVG, för tryck. Skalbar utan hackiga kanter.

    SvgPathImage ritar BARA den svarta banan - filen blir genomskinlig. På
    vitt papper syns det inte, men lagd på färgat underlag eller en mörk sida
    inverteras koden och blir oläsbar. Vi lägger därför in en vit rektangel
    under banan. Slöjda har inte gjort det, se docs/swish-qr.md.
    """
    installning = symbol_installning or valj_symbol(symbol)
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
