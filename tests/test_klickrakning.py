"""HEAD mot en kortlänk är en kontroll, inte ett klick: övervakning och
förhandsvisningar får inte driva upp statistiken."""

from app import database


def _skapa_lank(code: str = "hsandkist") -> int:
    with database.get_db() as db:
        db.execute(
            "INSERT INTO links (code, target_url, status) VALUES (?, ?, 1)",
            (code, "https://www.svenskakyrkan.se/harnosand/kist"),
        )
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def _antal_klick(link_id: int) -> int:
    with database.get_db() as db:
        return db.execute("SELECT COUNT(*) FROM clicks WHERE link_id=?", (link_id,)).fetchone()[0]


def test_head_omdirigerar_men_raknas_inte(client):
    link_id = _skapa_lank()
    response = client.head("/hsandkist")
    assert response.status_code == 302
    assert response.headers["location"].startswith("https://www.svenskakyrkan.se/")
    assert _antal_klick(link_id) == 0
    with database.get_db() as db:
        assert db.execute("SELECT last_used_at FROM links WHERE id=?", (link_id,)).fetchone()[0] is None


def test_get_raknas_som_klick(client):
    link_id = _skapa_lank()
    assert client.get("/hsandkist").status_code == 302
    assert _antal_klick(link_id) == 1
