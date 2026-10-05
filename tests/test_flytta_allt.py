"""Flytta allt från en användare: GET visar länkar, samlingar och om mottagaren
finns, utan att flytta något. POST med CSRF flyttar."""

from app import database


def _skapa(email: str, lankar: int, samlingar: int = 0) -> int:
    with database.get_db() as db:
        db.execute("INSERT INTO users (email) VALUES (?)", (email,))
        uid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for i in range(lankar):
            db.execute(
                "INSERT INTO links (code, target_url, owner_id, status) VALUES (?, ?, ?, 1)",
                (f"{email.split('@')[0]}{i}", "https://www.svenskakyrkan.se/x", uid),
            )
        for i in range(samlingar):
            db.execute(
                "INSERT INTO bundles (code, name, owner_id) VALUES (?, ?, ?)",
                (f"saml{email.split('@')[0]}{i}", f"Samling {i}", uid),
            )
        return uid


def _agda(uid: int) -> tuple[int, int]:
    with database.get_db() as db:
        return (
            db.execute("SELECT COUNT(*) FROM links WHERE owner_id=?", (uid,)).fetchone()[0],
            db.execute("SELECT COUNT(*) FROM bundles WHERE owner_id=?", (uid,)).fetchone()[0],
        )


def test_forhandsvisningen_visar_innehall_och_att_mottagaren_saknas(client, admin):
    uid = _skapa("gammal@svenskakyrkan.se", 3, 1)
    r = client.get(f"/admin/users/{uid}/flytta-allt", params={"new_email": "Ny@svenskakyrkan.se"})
    assert r.status_code == 200
    assert "Ja, flytta 3 länk(ar) och 1 samling(ar)" in r.text
    assert "Kontot finns inte och skapas vid flytten" in r.text
    assert "gammal0" in r.text and "samlgammal0" in r.text
    assert _agda(uid) == (3, 1)
    with database.get_db() as db:
        assert (
            db.execute("SELECT id FROM users WHERE email='ny@svenskakyrkan.se'").fetchone() is None
        )


def test_forhandsvisningen_visar_befintlig_mottagare(client, admin):
    uid = _skapa("gammal@svenskakyrkan.se", 1)
    _skapa("ny@svenskakyrkan.se", 2)
    r = client.get(f"/admin/users/{uid}/flytta-allt", params={"new_email": "ny@svenskakyrkan.se"})
    assert "Kontot finns" in r.text and "2 länk(ar)" in r.text


def test_ogiltig_eller_samma_adress_avvisas_i_bada_stegen(client, admin, hamta_csrf_token):
    uid = _skapa("gammal@svenskakyrkan.se", 1)
    r = client.get(f"/admin/users/{uid}/flytta-allt", params={"new_email": "inte-en-adress"})
    assert r.status_code == 303 and "delete_error" in r.headers["location"]
    token = hamta_csrf_token(client, "/admin/users")
    r = client.post(
        f"/admin/users/{uid}/transfer-all",
        data={"new_email": "gammal@svenskakyrkan.se", "csrf_token": token},
    )
    assert r.status_code == 303 and "samma+konto" in r.headers["location"]
    assert _agda(uid) == (1, 0)


def test_post_flyttar_allt_och_loggar(client, admin, hamta_csrf_token):
    uid = _skapa("gammal@svenskakyrkan.se", 2, 1)
    token = hamta_csrf_token(
        client, f"/admin/users/{uid}/flytta-allt?new_email=ny@svenskakyrkan.se"
    )
    r = client.post(
        f"/admin/users/{uid}/transfer-all",
        data={"new_email": "ny@svenskakyrkan.se", "csrf_token": token},
    )
    assert r.status_code == 303
    assert _agda(uid) == (0, 0)
    with database.get_db() as db:
        ny = db.execute("SELECT id FROM users WHERE email='ny@svenskakyrkan.se'").fetchone()[0]
        antal_logg = db.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action IN ('transfer','admin_bundle_transfer')"
        ).fetchone()[0]
    assert _agda(ny) == (2, 1)
    assert antal_logg == 3


def test_vanlig_anvandare_slapps_inte_in(client, inloggad_anvandare):
    uid = _skapa("gammal@svenskakyrkan.se", 1)
    r = client.get(f"/admin/users/{uid}/flytta-allt", params={"new_email": "ny@svenskakyrkan.se"})
    assert r.status_code in (302, 303)
    assert _agda(uid) == (1, 0)


def test_anvandarlistan_pekar_pa_forhandsvisningen(client, admin):
    uid = _skapa("gammal@svenskakyrkan.se", 1)
    html = client.get("/admin/users").text
    assert f'action="/admin/users/{uid}/flytta-allt" method="get"' in html
    assert f"/admin/users/{uid}/transfer-all" not in html
