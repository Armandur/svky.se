"""Inga externa bibliotek i mallarna.

Går CDN:et ner ska statistikgrafer, dra-och-släpp och markdown-redigerarna
fungera ändå. Beslut 2026-09-09: allt tredjepartsskript ligger lokalt.

Proven letar efter ÅTERFALL. En ny mall som klistrar in en CDN-rad ser
alldeles rätt ut i en granskning, och felet syns först den dag tjänsten
är nere - alltså precis när ingen har tid att leta.
"""

import re
from pathlib import Path

import pytest

MALLAR = Path(__file__).resolve().parents[1] / "app" / "templates"
STATIC = Path(__file__).resolve().parents[1] / "app" / "static"

# Värdar som betyder "hämtas över internet". Listan är avsiktligt kort:
# den ska fånga de vanliga, inte vara en fullständig katalog.
CDN_MONSTER = re.compile(
    r"(cdn\.jsdelivr\.net|unpkg\.com|cdnjs\.cloudflare\.com|ajax\.googleapis\.com"
    r"|code\.jquery\.com|stackpath\.bootstrapcdn\.com)",
    re.I,
)


def _mallar() -> list[Path]:
    """Alla mallar utom e-post.

    Mail-mallarna undantas INTE av lättja: ett mail renderas i någon annans
    e-postklient, som varken har vår static-katalog eller kör våra skript.
    """
    return sorted(p for p in MALLAR.rglob("*.html") if "mail" not in p.parts)


def test_hittar_mallar_att_prova():
    """Faller provet för att katalogen är tom mäter resten ingenting."""
    assert len(_mallar()) > 20, "hittade misstänkt få mallar - stämmer sökvägen?"


@pytest.mark.parametrize("mall", _mallar(), ids=lambda p: p.name)
def test_mallen_hamtar_inget_over_internet(mall: Path):
    traff = CDN_MONSTER.search(mall.read_text(encoding="utf-8"))

    assert not traff, (
        f"{mall.name} hämtar {traff.group(0) if traff else ''} över internet. "
        "Lägg filen i app/static/ i stället - se docs eller _chartjs.html."
    )


@pytest.mark.parametrize(
    "fil",
    [
        "chart.umd.min.js",
        "sortable.min.js",
        "easymde.min.js",
        "easymde.min.css",
        "fontawesome-easymde.css",
        "fontawesome-webfont.woff2",
    ],
)
def test_biblioteket_finns_lokalt(fil: str):
    """Mallarna pekar på /static/. Pekar de på en fil som inte finns blir
    felet en tyst 404 och ett skript som aldrig kör."""
    sokvag = STATIC / fil

    assert sokvag.is_file(), f"app/static/{fil} saknas"
    assert sokvag.stat().st_size > 1000, f"app/static/{fil} är misstänkt liten"


def test_chartjs_laddas_via_ett_enda_include():
    """Versionen ska stå på ETT ställe.

    Det som skulle ändras om felet fanns: en vy får en egen script-tagg och
    uppgraderingen missar den. Provet räknar taggar, inte inkluderingar.
    """
    egna = [
        m.name
        for m in _mallar()
        if "chart.umd.min.js" in m.read_text(encoding="utf-8") and m.name != "_chartjs.html"
    ]

    assert egna == [], f"dessa laddar Chart.js själva i stället för via include: {egna}"
