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


def _samtidiga_atgarder(cell: str) -> int:
    """Hur många knappar en rad visar SAMTIDIGT.

    Knappar inuti ett {% if %}/{% elif %}/{% else %} utesluter varandra och
    räknas som en. Att bara räkna knappar hade sagt fyra där användaren ser
    tre - och att dra bort antalet grenar hade släppt igenom en fjärde
    ovillkorlig knapp, vilket är precis det regeln finns för att stoppa.
    """
    utanfor, i_gren, sett_gren = 0, 0, False
    for bit in re.split(r"({%-?\s*(?:if|elif|else|endif)\b.*?%})", cell, flags=re.S):
        if re.match(r"{%-?\s*(?:if|elif|else)\b", bit or ""):
            sett_gren = True
            continue
        if re.match(r"{%-?\s*endif\b", bit or ""):
            sett_gren = False
            continue
        n = len(re.findall(r'class="btn btn-\w+ btn-sm"', bit or ""))
        if sett_gren:
            i_gren = max(i_gren, n)
        else:
            utanfor += n
    return utanfor + i_gren


def test_links_har_hogst_tre_atgarder_per_rad():
    """Regel: högst tre åtgärder per rad, den fjärde hör hemma på
    detaljsidan. Fler knappar spränger kolumnen igen."""
    cell = _text("links.html").split('<td class="actions">')[1].split("</td>")[0]

    # Detalj + QR + en tredje som växlar mellan Avaktivera, Återaktivera
    # och Se samling.
    assert _samtidiga_atgarder(cell) == 3


def test_atgardsraknaren_ser_en_fjarde_knapp():
    """Räknaren ska falla på det den finns för att fånga.

    Utan det här provet vore det omätt om _samtidiga_atgarder ens reagerar -
    en räknare som alltid svarar tre godkänner också en fjärde knapp.
    """
    cell = _text("links.html").split('<td class="actions">')[1].split("</td>")[0]
    fore = _samtidiga_atgarder(cell)

    extra = cell + '\n<a class="btn btn-secondary btn-sm">Fjärde</a>'

    assert _samtidiga_atgarder(extra) == fore + 1


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


def test_domaner_slog_ihop_sina_tva_flaggkolumner():
    """Rubrikerna "Subdomäner" och "Fria URL:er" var bredare än sina egna
    På/Av-värden - orden kostade mer plats än det de beskrev."""
    text = _text("domains.html")

    assert "<th>Tillåter</th>" in text
    assert "<th>Subdomäner</th>" not in text
    assert "<th>Fria URL:er</th>" not in text
    # Förkortningen i knappen kräver att innebörden finns i title.
    assert text.count('title="Subdomäner') == 1
    assert text.count('title="Fria URL:er') == 1


def test_domaner_kortar_noteringen_utan_att_tappa_den():
    text = _text("domains.html")

    assert 'class="dom-note dom-anteckning"' in text
    assert "title=\"{{ d.note or '' }}\"" in text


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
