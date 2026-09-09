"""Adminlistornas bredd, kolumner och åtgärder.

Reglerna står i docs/design.md avsnitt 10. Proven här mäter det som går att
mäta utan webbläsare: att kolumnräkningen hänger ihop, att varje tabell har
sin svepbehållare, och att åtgärderna finns kvar. Själva bredden mäts i
browsern - se avsnittets kontrollstycke.
"""

import re
from pathlib import Path

import pytest

MALLAR = Path(__file__).resolve().parents[1] / "app" / "templates" / "admin"


def _text(namn: str) -> str:
    return (MALLAR / namn).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "mall",
    ["links.html", "bundles.html", "domains.html", "takeover_requests.html", "transfers.html"],
)
def test_varje_tabell_ligger_i_en_svepbehallare(mall):
    """En tabell utan .table-wrap är en bugg, inte ett val.

    admin/bundles.html saknade den och hamnade bakom overflow-x: hidden på
    föräldern - 621 px innehåll som inte gick att nå alls på en telefon.
    """
    text = _text(mall)
    if "<table" not in text:
        pytest.skip(f"{mall} har ingen tabell")

    # Räkna klassattributet och inte ordet: en kommentar som NÄMNER
    # table-wrap är inte en behållare, och ett prov som räknar den mäter
    # sin egen dokumentation.
    tabeller = len(re.findall(r"<table[ >]", text))
    behallare = len(re.findall(r'class="table-wrap"', text))

    assert tabeller == behallare, f"{mall}: {tabeller} tabeller men {behallare} .table-wrap"


def test_colspan_stammer_med_antalet_kolumner():
    """En colspan som glidit isär med kolumnerna syns först när den dolda
    raden öppnas, alltså sällan."""
    text = _text("links.html")
    kolumner = len(re.findall(r"<th[ >]", text))
    colspans = {int(n) for n in re.findall(r'colspan="(\d+)"', text)}

    assert colspans == {kolumner}, f"links.html har {kolumner} kolumner men colspan {colspans}"


def test_links_har_hogst_tre_atgarder_per_rad():
    """Regel: högst tre åtgärder per rad, den fjärde hör hemma på
    detaljsidan. Fler knappar spränger kolumnen igen."""
    text = _text("links.html")
    cell = text.split('<td class="actions">')[1].split("</td>")[0]

    knappar = len(re.findall(r'class="btn btn-\w+ btn-sm"', cell))
    grenar = cell.count("{% if") + cell.count("{% elif")

    # Detalj + QR + en tredje som växlar mellan tre varianter.
    assert knappar - grenar <= 3, f"fler än tre samtidiga åtgärder: {knappar - grenar}"


def test_datumkolumnerna_ar_sammanslagna():
    """Senast använd och Skapad svarade båda på 'när hände något'. En
    kolumn visar den senaste händelsen, den andra ligger i title."""
    text = _text("links.html")

    assert "<th>Senast händelse</th>" in text
    assert "<th>Skapad</th>" not in text
    assert 'title="Skapad {{ link.created_at | sthlm }}' in text


def test_agaren_kortas_men_hela_adressen_finns_kvar():
    """Regel: korta det som har en igenkännbar början, lägg hela värdet i
    title. Aldrig radbrytning för att spara bredd."""
    text = _text("links.html")

    assert "split('@')[0]" in text
    assert 'title="{{ link.owner_email' in text


def test_svepskriptet_laddas_globalt():
    bas = (MALLAR.parent / "base.html").read_text(encoding="utf-8")

    assert "/static/tabellsvep.js" in bas


def test_svepskriptet_satter_alla_fyra_lagen():
    """hoger, vanster, bada - och inget attribut när tabellen ryms."""
    js = (MALLAR.parents[1] / "static" / "tabellsvep.js").read_text(encoding="utf-8")

    for lage in ('"hoger"', '"vanster"', '"bada"'):
        assert lage in js
    assert "delete svep.dataset.mer" in js


def test_masken_finns_for_alla_lagen():
    css = (MALLAR.parents[1] / "static" / "style.css").read_text(encoding="utf-8")

    for lage in ("hoger", "vanster", "bada"):
        assert f'.table-wrap[data-mer="{lage}"]' in css, lage
    # Utan -webkit- syns ingenting i Safari på iOS, alltså på telefonen.
    assert css.count("-webkit-mask-image") >= 3
