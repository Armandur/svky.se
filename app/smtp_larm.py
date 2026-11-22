import logging
import os
import subprocess
from collections import deque
from threading import Lock, Thread
from time import monotonic

from app.config import MILJO

log = logging.getLogger(__name__)

_TROSKEL = 6
_TIMME = 3600
_fel = deque(maxlen=_TROSKEL)
_las = Lock()
_senaste_larmforsok = float("-inf")


def registrera_smtp_fel() -> None:
    global _senaste_larmforsok

    with _las:
        nu = monotonic()
        _fel.append(nu)
        if len(_fel) < _TROSKEL or nu - _fel[0] >= _TIMME:
            return
        if nu - _senaste_larmforsok < _TIMME:
            return
        # Ett tidsgränsfel kan betyda att ntfy redan tog emot larmet.
        _senaste_larmforsok = nu

    url = os.environ.get("NTFY_URL")
    token = os.environ.get("NTFY_TOKEN")
    if url and token:
        Thread(target=_skicka_larm, args=(url, token), daemon=True).start()


def _skicka_larm(url: str, token: str) -> None:
    titel = "svky.se staging / SMTP" if MILJO == "staging" else "svky.se / SMTP"
    text = (
        "Minst sex e-postutskick har misslyckats den senaste timmen.\n"
        "Inloggnings- och verifieringslänkar kan utebli. Kontrollera SMTP-driften."
    )
    try:
        resultat = subprocess.run(
            [
                "curl", "-q", "-fsS", "-m", "10", "--proto", "=https",
                "--header", "@-",
                "--header", f"Title: {titel}",
                "--header", "Priority: 3",
                "--header", "Tags: warning,email",
                "--data-binary", text,
                "--output", os.devnull,
                "--write-out", "%{http_code}",
                "--", f"{url.rstrip('/')}/svc_ops",
            ],
            input=f"Authorization: Bearer {token}\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=12,
            check=True,
        )
        skickat = resultat.stdout.startswith("2")
    except (OSError, subprocess.SubprocessError):
        skickat = False
    if not skickat:
        log.warning("Kunde inte skicka SMTP-larm via ntfy.")
