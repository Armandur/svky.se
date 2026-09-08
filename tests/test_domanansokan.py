from app import database
from app.auth import COOKIE_NAME, create_session_cookie


def _logga_in(client, email: str, is_admin: bool = False) -> int:
    with database.get_db() as db:
        db.execute(
            "INSERT INTO users (email, is_admin, allow_external_urls) VALUES (?, ?, 0)",
            (email, int(is_admin)),
        )
        user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    client.cookies.set(COOKIE_NAME, create_session_cookie(user_id))
    return user_id


def _skapa_ansokan(user_id: int, reason: str = "Behöver länka till vårt bokningssystem.") -> int:
    with database.get_db() as db:
        db.execute(
            "INSERT INTO domain_permission_requests (user_id, permission, reason) "
            "VALUES (?, 'external_urls', ?)",
            (user_id, reason),
        )
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def _lage(user_id: int, request_id: int) -> tuple[int, str]:
    with database.get_db() as db:
        allowed = db.execute(
            "SELECT allow_external_urls FROM users WHERE id=?", (user_id,)
        ).fetchone()[0]
        status = db.execute(
            "SELECT status FROM domain_permission_requests WHERE id=?", (request_id,)
        ).fetchone()[0]
    return allowed, status


def test_utloggad_skickas_till_login(client):
    response = client.get("/mina-lankar/domanansokan")

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_vanlig_anvandare_nar_inte_adminvyn(client):
    _logga_in(client, "sokande@svenskakyrkan.se")

    response = client.get("/admin/domanansokningar")

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_post_utan_giltig_csrf_sparar_ingenting(client):
    _logga_in(client, "sokande@svenskakyrkan.se")

    response = client.post(
        "/mina-lankar/domanansokan",
        data={"reason": "Ett tydligt behov", "csrf_token": "fel"},
    )

    assert response.status_code == 403
    with database.get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM domain_permission_requests").fetchone()[0]
    assert count == 0


def test_tom_motivering_sparas_inte(client, hamta_csrf_token):
    _logga_in(client, "sokande@svenskakyrkan.se")
    csrf = hamta_csrf_token(client, "/mina-lankar/domanansokan")

    response = client.post(
        "/mina-lankar/domanansokan",
        data={"reason": "   ", "csrf_token": csrf},
    )

    assert response.status_code == 422
    with database.get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM domain_permission_requests").fetchone()[0]
    assert count == 0


def test_en_andra_ansokan_avvisas_medan_den_forsta_vantar(
    client, hamta_csrf_token
):
    _logga_in(client, "sokande@svenskakyrkan.se")
    csrf = hamta_csrf_token(client, "/mina-lankar/domanansokan")

    first = client.post(
        "/mina-lankar/domanansokan",
        data={"reason": "Första motiveringen", "csrf_token": csrf},
    )
    second = client.post(
        "/mina-lankar/domanansokan",
        data={"reason": "Andra motiveringen", "csrf_token": csrf},
    )

    assert first.status_code == 303
    assert second.status_code == 303
    assert second.headers["location"].endswith("?vantar=1")
    with database.get_db() as db:
        rows = db.execute(
            "SELECT reason FROM domain_permission_requests"
        ).fetchall()
    assert [row["reason"] for row in rows] == ["Första motiveringen"]


def test_vanlig_anvandare_kan_inte_godkanna_sin_ansokan(
    client, hamta_csrf_token
):
    user_id = _logga_in(client, "sokande@svenskakyrkan.se")
    csrf = hamta_csrf_token(client, "/mina-lankar/domanansokan")
    request_id = _skapa_ansokan(user_id)
    before = _lage(user_id, request_id)
    assert before == (0, "pending")

    response = client.post(
        f"/admin/domanansokningar/{request_id}/approve",
        data={"csrf_token": csrf},
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert _lage(user_id, request_id) == before


def test_adminbeslut_utan_giltig_csrf_andrar_ingenting(client):
    user_id = _logga_in(client, "sokande@svenskakyrkan.se")
    request_id = _skapa_ansokan(user_id)
    client.cookies.clear()
    _logga_in(client, "admin@svenskakyrkan.se", is_admin=True)

    response = client.post(
        f"/admin/domanansokningar/{request_id}/approve",
        data={"csrf_token": "fel"},
    )

    assert response.status_code == 403
    assert _lage(user_id, request_id) == (0, "pending")


def test_godkannande_satter_flaggan_och_skickar_epost(
    client, hamta_csrf_token, monkeypatch
):
    user_id = _logga_in(client, "sokande@svenskakyrkan.se")
    request_id = _skapa_ansokan(user_id)
    client.cookies.clear()
    _logga_in(client, "admin@svenskakyrkan.se", is_admin=True)
    csrf = hamta_csrf_token(client, "/admin/domanansokningar")
    sent = []
    monkeypatch.setattr(
        "app.routes.admin.domain_requests.skicka_domanansokan_godkand",
        lambda email, base_url: sent.append((email, base_url)),
    )

    response = client.post(
        f"/admin/domanansokningar/{request_id}/approve",
        data={"csrf_token": csrf},
    )

    assert response.status_code == 303
    assert _lage(user_id, request_id) == (1, "approved")
    assert sent and sent[0][0] == "sokande@svenskakyrkan.se"


def test_avslag_satter_inte_flaggan_och_skickar_epost(
    client, hamta_csrf_token, monkeypatch
):
    user_id = _logga_in(client, "sokande@svenskakyrkan.se")
    request_id = _skapa_ansokan(user_id)
    client.cookies.clear()
    _logga_in(client, "admin@svenskakyrkan.se", is_admin=True)
    csrf = hamta_csrf_token(client, "/admin/domanansokningar")
    sent = []
    monkeypatch.setattr(
        "app.routes.admin.domain_requests.skicka_domanansokan_avslagen",
        lambda email: sent.append(email),
    )

    response = client.post(
        f"/admin/domanansokningar/{request_id}/reject",
        data={"csrf_token": csrf},
    )

    assert response.status_code == 303
    assert _lage(user_id, request_id) == (0, "rejected")
    assert sent == ["sokande@svenskakyrkan.se"]


def test_adminbaren_renderar_utan_att_routen_skickar_raknaren(client, admin):
    """Badgen får inte fälla en vy som inte känner till den.

    Ett första försök smugglade räknaren i en int-subklass från
    pending_takeover_count. Två admin-vyer skickar inget värde alls, och
    Jinja kastade då UndefinedError på attributet - hela sidan dog. Räknaren
    är därför en global, och provet går genom vyer som INTE skickar den.
    """
    for sida in ("/admin/links", "/admin/users", "/admin/stats", "/admin/domaner"):
        svar = client.get(sida)

        assert svar.status_code == 200, f"{sida} svarade {svar.status_code}"
        assert "Extern länkning" in svar.text
