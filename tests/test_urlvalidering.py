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
