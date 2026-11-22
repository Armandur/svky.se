from collections import deque
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Thread

import pytest

from app import mail, smtp_larm

MOTTAGARE = "prov@svenskakyrkan.se"
SMTP_FELTEXT = f"550 nekad för {MOTTAGARE}, SMTP-lösenord och intern feltext"
LOGIN_URL = "https://svky.example/auth/hemlig-engangsbricka"


@pytest.fixture
def larmprov(monkeypatch):
    klocka = [0]
    anrop = []
    tradar = []

    class Larmtrad(Thread):
        def start(self):
            super().start()
            tradar.append(self)

    def simulerad_transport(argument, **kwargs):
        anrop.append((argument, kwargs["input"]))
        return smtp_larm.subprocess.CompletedProcess(argument, 0, stdout="200")

    def vanta_pa_larm():
        for trad in tradar:
            trad.join(timeout=2)
            assert not trad.is_alive()

    monkeypatch.setenv("NTFY_URL", "https://ntfy.example/")
    monkeypatch.setenv("NTFY_TOKEN", "syntetisk-larmtoken")
    monkeypatch.setattr(smtp_larm, "_fel", deque(maxlen=smtp_larm._TROSKEL))
    monkeypatch.setattr(smtp_larm, "_senaste_larmforsok", float("-inf"))
    monkeypatch.setattr(smtp_larm, "monotonic", lambda: klocka[0])
    monkeypatch.setattr(smtp_larm, "Thread", Larmtrad)
    monkeypatch.setattr(smtp_larm.subprocess, "run", simulerad_transport)

    def trasig_smtp(*args, **kwargs):
        raise mail.smtplib.SMTPDataError(550, SMTP_FELTEXT.encode())

    monkeypatch.setattr(mail.smtplib, "SMTP", trasig_smtp)
    yield klocka, anrop, vanta_pa_larm
    vanta_pa_larm()


def _gor_smtp_fel(antal=1):
    for _ in range(antal):
        with pytest.raises(mail.MailError) as fel:
            mail.skicka_loginmail(MOTTAGARE, LOGIN_URL)
        assert isinstance(fel.value.__cause__, mail.smtplib.SMTPDataError)
        assert str(fel.value) == str(fel.value.__cause__)


def test_sjatte_fel_larmar_och_sparren_slapps_efter_en_timme(larmprov):
    klocka, anrop, vanta_pa_larm = larmprov
    _gor_smtp_fel(5)
    vanta_pa_larm()
    assert anrop == []

    _gor_smtp_fel()
    vanta_pa_larm()
    assert len(anrop) == 1
    argument, stdin = anrop[0]
    assert argument[-1] == "https://ntfy.example/svc_ops"
    assert "Priority: 3" in argument
    assert stdin == "Authorization: Bearer syntetisk-larmtoken\n"
    assert "syntetisk-larmtoken" not in str(argument)
    for skyddad_text in (MOTTAGARE, LOGIN_URL, "SMTP-lösenord", "intern feltext"):
        assert skyddad_text not in str(anrop)

    klocka[0] = 3599
    _gor_smtp_fel(6)
    vanta_pa_larm()
    assert len(anrop) == 1

    klocka[0] = 3600
    _gor_smtp_fel()
    vanta_pa_larm()
    assert len(anrop) == 2


def test_fel_som_ar_en_timme_gamla_raknas_bort(larmprov):
    klocka, anrop, vanta_pa_larm = larmprov
    _gor_smtp_fel(5)
    klocka[0] = 3600
    _gor_smtp_fel()
    vanta_pa_larm()
    assert anrop == []

    _gor_smtp_fel(5)
    vanta_pa_larm()
    assert len(anrop) == 1


def test_samtidiga_smtp_fel_ger_ett_larm(larmprov):
    _, anrop, vanta_pa_larm = larmprov
    antal = 12
    start = Barrier(antal)

    def fel():
        start.wait(timeout=2)
        _gor_smtp_fel()

    with ThreadPoolExecutor(max_workers=antal) as pool:
        jobb = [pool.submit(fel) for _ in range(antal)]
        for resultat in jobb:
            resultat.result(timeout=5)

    vanta_pa_larm()
    assert len(anrop) == 1


def test_smtp_fel_utan_ntfy_token_skickar_inget_larm(larmprov, monkeypatch):
    _, anrop, vanta_pa_larm = larmprov
    monkeypatch.delenv("NTFY_TOKEN")
    _gor_smtp_fel(6)
    vanta_pa_larm()
    assert anrop == []


def test_smtp_felet_finns_kvar_nar_larmtraden_inte_kan_starta(larmprov, monkeypatch, caplog):
    _, anrop, vanta_pa_larm = larmprov

    def trasig_trad(*args, **kwargs):
        raise RuntimeError("Simulerat trådfel")

    monkeypatch.setattr(smtp_larm, "Thread", trasig_trad)
    _gor_smtp_fel(6)
    vanta_pa_larm()
    assert anrop == []
    assert "Kunde inte starta SMTP-larmet." in caplog.messages


def test_login_ger_samma_felsvar_nar_larmtransporten_fallerar(
    larmprov, client, hamta_csrf_token, monkeypatch, caplog
):
    _, anrop, vanta_pa_larm = larmprov

    def trasig_transport(argument, **kwargs):
        anrop.append(argument)
        raise smtp_larm.subprocess.TimeoutExpired(argument, 12)

    monkeypatch.setattr(smtp_larm.subprocess, "run", trasig_transport)
    data = {"email": MOTTAGARE, "csrf_token": hamta_csrf_token(client)}
    forsta_svar = client.post("/login", data=data)
    assert forsta_svar.status_code == 200
    assert "Inloggningsmail kunde inte skickas just nu." in forsta_svar.text

    _gor_smtp_fel(4)
    vanta_pa_larm()
    assert anrop == []
    svar_vid_larm = client.post("/login", data=data)
    vanta_pa_larm()
    assert len(anrop) == 1
    assert "Kunde inte skicka SMTP-larm via ntfy." in caplog.messages
    assert svar_vid_larm.status_code == forsta_svar.status_code
    assert svar_vid_larm.content == forsta_svar.content

    _gor_smtp_fel(6)
    vanta_pa_larm()
    assert len(anrop) == 1
