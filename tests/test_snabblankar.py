"""Admininställningar för snabblänkarna på startsidan."""

from app import database


def test_introredigeraren_sparar_markdown_i_databasen(client, admin, hamta_csrf_token):
    token = hamta_csrf_token(client, "/admin/snabblänkar")
    markdown = "## Hitta rätt\n\nVälj en **snabblänk** i listan."

    svar = client.post(
        "/admin/snabblänkar/update-intro",
        data={
            "intro_md": markdown,
            "heading": "Snabblänkar",
            "subtitle": "Ofta använda länkar",
            "csrf_token": token,
        },
    )

    assert svar.status_code == 303
    with database.get_db() as db:
        sparat = db.execute(
            "SELECT value FROM site_settings WHERE key='snabblänkar_intro'"
        ).fetchone()
    assert sparat is not None
    assert sparat["value"] == markdown
