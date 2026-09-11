from app import database
from app.auth import COOKIE_NAME, create_session_cookie
from app.validation import MAX_TEXT_LENGTH

URL_FORE = "https://www.svenskakyrkan.se/fore"
URL_EFTER = "https://www.svenskakyrkan.se/efter"


def _skapa_lank(owner_id: int, note: str | None = "Gammal notering") -> int:
    with database.get_db() as db:
        db.execute(
            """INSERT INTO links (code, target_url, owner_id, status, note)
               VALUES ('min-notering', ?, ?, 1, ?)""",
            (URL_FORE, owner_id, note),
        )
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def _uppdatera(client, hamta_csrf_token, link_id: int, target_url: str, note: str):
    return client.post(
        f"/mina-lankar/{link_id}/update",
        data={
            "target_url": target_url,
            "note": note,
            "csrf_token": hamta_csrf_token(client, "/mina-lankar"),
        },
    )


def _las_lank(link_id: int):
    with database.get_db() as db:
        return db.execute("SELECT target_url, note FROM links WHERE id=?", (link_id,)).fetchone()


def test_agaren_sparar_ny_notering_som_syns_i_bada_vyerna(
    client, inloggad_anvandare, hamta_csrf_token
):
    link_id = _skapa_lank(inloggad_anvandare["id"], None)

    svar = _uppdatera(client, hamta_csrf_token, link_id, URL_FORE, "Ny notering")

    assert svar.status_code == 303
    assert _las_lank(link_id)["note"] == "Ny notering"
    assert "Ny notering" in client.get("/mina-lankar").text
    assert "Ny notering" in client.get(f"/mina-lankar/{link_id}").text


def test_agaren_kan_tomma_noteringen(client, inloggad_anvandare, hamta_csrf_token):
    link_id = _skapa_lank(inloggad_anvandare["id"])

    svar = _uppdatera(client, hamta_csrf_token, link_id, URL_FORE, "")

    assert svar.status_code == 303
    assert _las_lank(link_id)["note"] is None


def test_bara_noteringen_andras_utan_att_urlen_rors(client, inloggad_anvandare, hamta_csrf_token):
    link_id = _skapa_lank(inloggad_anvandare["id"])

    _uppdatera(client, hamta_csrf_token, link_id, URL_FORE, "Ersatt notering")

    link = _las_lank(link_id)
    assert link["target_url"] == URL_FORE
    assert link["note"] == "Ersatt notering"


def test_bara_urlen_andras_utan_att_noteringen_rors(client, inloggad_anvandare, hamta_csrf_token):
    link_id = _skapa_lank(inloggad_anvandare["id"])

    _uppdatera(client, hamta_csrf_token, link_id, URL_EFTER, "Gammal notering")

    link = _las_lank(link_id)
    assert link["target_url"] == URL_EFTER
    assert link["note"] == "Gammal notering"


def test_en_annan_anvandare_kan_inte_andra_noteringen(client, inloggad_anvandare, hamta_csrf_token):
    link_id = _skapa_lank(inloggad_anvandare["id"])
    with database.get_db() as db:
        db.execute("INSERT INTO users (email) VALUES ('annan@svenskakyrkan.se')")
        annan_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    client.cookies.set(COOKIE_NAME, create_session_cookie(annan_id))

    svar = _uppdatera(client, hamta_csrf_token, link_id, URL_EFTER, "Kapad")

    assert svar.status_code == 404
    link = _las_lank(link_id)
    assert link["target_url"] == URL_FORE
    assert link["note"] == "Gammal notering"


def test_for_lang_notering_avvisas_och_inskriven_text_foljer_med(
    client, inloggad_anvandare, hamta_csrf_token
):
    link_id = _skapa_lank(inloggad_anvandare["id"])
    inskriven_url = URL_EFTER
    inskriven_notering = "å" * (MAX_TEXT_LENGTH + 1)

    svar = _uppdatera(client, hamta_csrf_token, link_id, inskriven_url, inskriven_notering)

    assert svar.status_code == 422
    assert "Noteringen får vara högst 2000 tecken." in svar.text
    assert inskriven_url in svar.text
    assert inskriven_notering in svar.text
    link = _las_lank(link_id)
    assert link["target_url"] == URL_FORE
    assert link["note"] == "Gammal notering"
