"""Spärren mot kortlänkar som pekar tillbaka på svky.se.

En kod som leder till svky.se är antingen ett misstag eller en loop, och en
självrefererande kod märks först när någon klickar. Spärren gäller ÄVEN admin
och trusted-användare, alltså också när allow_external är sant - beslut av
Rasmus 2026-09-10.

Proven jämför mot EASTER_EGG-konstanten nedan. Ändras texten i app/validation.py
faller de, vilket är meningen: texten är en del av det som beslutats, inte en
detalj som får glida.
"""

import pytest

from app.validation import validate_target_url

EASTER_EGG = "Ormen får inte äta sin egen svans. Ange adressen till sidan du vill nå i stället."


def test_svky_se_avvisas():
    assert validate_target_url("https://svky.se/nagot") == EASTER_EGG


def test_subdoman_till_svky_se_avvisas():
    assert validate_target_url("https://www.svky.se/nagot") == EASTER_EGG


def test_svky_se_avvisas_aven_for_betrodda_anvandare():
    assert validate_target_url("https://svky.se/nagot", allow_external=True) == EASTER_EGG


@pytest.mark.parametrize(
    "url",
    [
        "https://svky.se:443/nagot",
        "https://nagon@svky.se/nagot",
    ],
)
def test_port_och_anvandarinfo_kan_inte_ga_runt_sparren(url):
    assert validate_target_url(url, allow_external=True) == EASTER_EGG


def test_svenskakyrkan_se_paverkas_inte(client):
    assert validate_target_url("https://www.svenskakyrkan.se/nagot") is None


def test_bestall_visar_easter_egg_for_svky_se(client, inloggad_anvandare, hamta_csrf_token):
    svar = client.post(
        "/bestall",
        data={
            "target_url": "https://svky.se/nagot",
            "code": "ormbo",
            "csrf_token": hamta_csrf_token(client, "/bestall"),
        },
    )

    assert svar.status_code == 422
    assert EASTER_EGG in svar.text


# --- ormen på beställningssidan ------------------------------------------


def test_bestall_ritar_ormen_vid_sjalvreferens(client, inloggad_anvandare, hamta_csrf_token):
    """Ormen ska finnas i svaret, och skriptet som ritar den."""
    svar = client.post(
        "/bestall",
        data={
            "target_url": "https://svky.se/nagot",
            "code": "ormbo",
            "csrf_token": hamta_csrf_token(client, "/bestall"),
        },
    )

    assert 'id="orm-canvas"' in svar.text
    assert "/static/orm.js" in svar.text


def test_bestall_ritar_INGEN_orm_vid_andra_fel(client, inloggad_anvandare, hamta_csrf_token):
    """Det som skulle ändras om felet fanns: flaggan sätts för varje
    URL-fel i stället för bara självreferensen, och en avvisad domän får en
    orm den inte ska ha.

    Provet är hela poängen med att flaggan finns. Utan det kunde man lika
    gärna ritat ormen vid `errors.target_url`.
    """
    svar = client.post(
        "/bestall",
        data={
            "target_url": "http://www.svenskakyrkan.se/nagot",
            "code": "annat",
            "csrf_token": hamta_csrf_token(client, "/bestall"),
        },
    )

    # http och inte https avvisas oavsett behörighet, till skillnad från en
    # okänd domän som en trusted användare släpps förbi med.
    assert "måste börja med https" in svar.text, "provet mäter fel fel"
    assert 'id="orm-canvas"' not in svar.text
    assert "/static/orm.js" not in svar.text


def test_ormen_finns_som_lokal_fil():
    """Mallen pekar på /static/orm.js. Pekar den på en fil som inte finns
    blir felet en tyst 404 och en ruta som står tom."""
    from pathlib import Path

    fil = Path(__file__).resolve().parents[1] / "app" / "static" / "orm.js"

    assert fil.is_file()
    text = fil.read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in text, "reducerad rörelse ska hanteras"
    assert "cdn." not in text and "http" not in text.replace("https://", "")
