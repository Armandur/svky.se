"""Nollställning av en länks klick: GET visar vad som raderas utan att röra
något, POST med CSRF raderar och loggar. Samma mönster som engångslänkarna."""

import re

from app import database


def _skapa_lank_med_klick(antal: int, code: str = "hsandkist") -> int:
    with database.get_db() as db:
        db.execute(
            "INSERT INTO links (code, target_url, status, last_used_at) VALUES (?, ?, 1, CURRENT_TIMESTAMP)",
            (code, "https://www.svenskakyrkan.se/harnosand/kist"),
        )
        link_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for _ in range(antal):
            db.execute("INSERT INTO clicks (link_id) VALUES (?)", (link_id,))
        return link_id


def _antal_klick(link_id: int) -> int:
    with database.get_db() as db:
        return db.execute("SELECT COUNT(*) FROM clicks WHERE link_id=?", (link_id,)).fetchone()[0]


def test_forhandsvisningen_visar_antalet_men_raderar_inget(client, admin):
    link_id = _skapa_lank_med_klick(7)
    annan = _skapa_lank_med_klick(3, code="annan")
    response = client.get(f"/admin/links/{link_id}/nollstall-klick")
    assert response.status_code == 200
    assert "Ja, radera 7 klick" in response.text
    assert _antal_klick(link_id) == 7
    assert _antal_klick(annan) == 3


def test_post_raderar_bara_lankens_klick_och_loggar(client, admin, hamta_csrf_token):
    link_id = _skapa_lank_med_klick(7)
    annan = _skapa_lank_med_klick(3, code="annan")
    token = hamta_csrf_token(client, f"/admin/links/{link_id}/nollstall-klick")
    response = client.post(f"/admin/links/{link_id}/nollstall-klick", data={"csrf_token": token})
    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/links/{link_id}?nollstallt=7"
    assert _antal_klick(link_id) == 0
    assert _antal_klick(annan) == 3
    with database.get_db() as db:
        assert db.execute("SELECT last_used_at FROM links WHERE id=?", (link_id,)).fetchone()[0] is None
        logg = db.execute(
            "SELECT action, detail FROM audit_log WHERE link_id=?", (link_id,)
        ).fetchone()
    assert logg["action"] == "admin_nollstall_klick" and "7 klick" in logg["detail"]
    detalj = client.get(response.headers["location"])
    assert "7 klick raderade" in detalj.text


def test_post_utan_giltig_csrf_raderar_inget(client, admin):
    link_id = _skapa_lank_med_klick(2)
    response = client.post(f"/admin/links/{link_id}/nollstall-klick", data={"csrf_token": "fel"})
    assert response.status_code == 403
    assert _antal_klick(link_id) == 2


def test_vanlig_anvandare_slapps_inte_in(client, inloggad_anvandare, hamta_csrf_token):
    link_id = _skapa_lank_med_klick(2)
    assert client.get(f"/admin/links/{link_id}/nollstall-klick").status_code in (302, 303)
    token = hamta_csrf_token(client, "/bestall")
    response = client.post(f"/admin/links/{link_id}/nollstall-klick", data={"csrf_token": token})
    assert response.status_code in (302, 303)
    assert _antal_klick(link_id) == 2


def test_lankdetaljen_lankar_till_nollstallningen(client, admin):
    link_id = _skapa_lank_med_klick(1)
    html = client.get(f"/admin/links/{link_id}").text
    assert re.search(rf'href="/admin/links/{link_id}/nollstall-klick"', html)
