"""Swish-samlingen: ägarens rutter, den publika sidan och tryckräkningen.

Proven anropar ROUTERNA, inte hjälpfunktionerna under dem. Det är där
behörighetsspärren, omdirigeringen och beskedet bor, och det är dem som
brister om något gått fel.
"""

import io
import re

import pytest
from PIL import Image

from app.database import get_db

MOTTAGARE = "1231234567"


def _zxing(png: bytes) -> str | None:
    """Avkodar med zxing-cpp, samma familj som telefonernas läsare."""
    import zxingcpp

    traff = zxingcpp.read_barcode(Image.open(io.BytesIO(png)).convert("RGB"))
    return traff.text if traff else None


def _csrf(client, route: str) -> str:
    svar = client.get(route)
    assert svar.status_code == 200, route
    trafF = re.search(r'name="csrf_token" value="([^"]+)"', svar.text)
    assert trafF, f"{route} saknar csrf_token"
    return trafF.group(1)


def _annan_anvandare() -> int:
    with get_db() as db:
        db.execute("INSERT INTO users (email) VALUES ('annan@svenskakyrkan.se')")
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def _samling(agare: int, code: str = "domkyrkan", status: int = 1) -> int:
    with get_db() as db:
        db.execute(
            "INSERT INTO bundles (code, name, owner_id, status, theme) VALUES (?,?,?,?,'swish')",
            (code, "Ge en gåva", agare, status),
        )
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def _post(bundle_id: int, title: str = "Diakoni", belopp: str | None = "100,00", **kw) -> int:
    falt = {
        "mottagare": MOTTAGARE,
        "meddelande": title,
        "fri_mottagare": 0,
        "fritt_belopp": 0 if belopp else 1,
        "fritt_meddelande": 0,
        "sort_order": 1,
    }
    falt.update(kw)
    with get_db() as db:
        db.execute(
            """INSERT INTO swish_items
               (bundle_id, title, mottagare, belopp, meddelande,
                fri_mottagare, fritt_belopp, fritt_meddelande, sort_order)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                bundle_id,
                title,
                falt["mottagare"],
                belopp,
                falt["meddelande"],
                falt["fri_mottagare"],
                falt["fritt_belopp"],
                falt["fritt_meddelande"],
                falt["sort_order"],
            ),
        )
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


# --- publika sidan -------------------------------------------------------


def test_samlingen_visar_alla_andamal(client, inloggad_anvandare):
    """Hela poängen: tre koder på lappen ersätts av en kod och en sida."""
    bundle_id = _samling(inloggad_anvandare["id"])
    for namn in ("Diakoni", "Musikverksamheten", "Dagens kollekt"):
        _post(bundle_id, namn, belopp=None if namn == "Dagens kollekt" else "100,00")

    svar = client.get("/domkyrkan")

    assert svar.status_code == 200
    for namn in ("Diakoni", "Musikverksamheten", "Dagens kollekt"):
        assert namn in svar.text


def test_sidan_bar_bade_knapp_och_kod_for_varje_post(client, inloggad_anvandare):
    """Visa aldrig bara det ena. Vilket som är störst avgörs i webbläsaren,
    men båda MÅSTE finnas i svaret - annars kan enhetsvalet låsa ute någon."""
    bundle_id = _samling(inloggad_anvandare["id"])
    item_id = _post(bundle_id)

    text = client.get("/domkyrkan").text

    assert "swish://payment?data=" in text
    assert f"/swish-post/{item_id}/qr.png" in text
    assert "Jag ska skanna i stället" in text


def test_avaktiverad_samling_ger_404(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"], status=3)
    _post(bundle_id)

    assert client.get("/domkyrkan").status_code == 404


def test_koden_avkodas_till_swishstrangen(client, inloggad_anvandare):
    """Bilden på sidan ska bära en betalning Swish-appen förstår, inte en
    länk tillbaka hit."""
    bundle_id = _samling(inloggad_anvandare["id"])
    item_id = _post(bundle_id, "Diakoni", belopp="100,00")

    svar = client.get(f"/swish-post/{item_id}/qr.png")

    assert svar.status_code == 200
    assert _zxing(svar.content) == f"C{MOTTAGARE};100,00;Diakoni;0"


def test_kod_ur_avaktiverad_samling_ger_404(client, inloggad_anvandare):
    """Bildadressen får inte överleva att samlingen stängs av."""
    bundle_id = _samling(inloggad_anvandare["id"], status=3)
    item_id = _post(bundle_id)

    assert client.get(f"/swish-post/{item_id}/qr.png").status_code == 404


def test_okand_andelse_ger_404(client, inloggad_anvandare):
    item_id = _post(_samling(inloggad_anvandare["id"]))

    assert client.get(f"/swish-post/{item_id}/qr.gif").status_code == 404


# --- tryckräkningen ------------------------------------------------------


def test_tryck_raknas(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"])
    item_id = _post(bundle_id)

    assert client.post(f"/swish-post/{item_id}/tryck").status_code == 204
    assert client.post(f"/swish-post/{item_id}/tryck").status_code == 204

    with get_db() as db:
        antal = db.execute(
            "SELECT COUNT(*) AS n FROM swish_taps WHERE swish_item_id=?", (item_id,)
        ).fetchone()["n"]
    assert antal == 2


def test_tryck_pa_avaktiverad_samling_ger_404(client, inloggad_anvandare):
    item_id = _post(_samling(inloggad_anvandare["id"], status=3))

    assert client.post(f"/swish-post/{item_id}/tryck").status_code == 404


# --- ägarens vy ----------------------------------------------------------


def test_agarvyn_visar_swishformularet(client, inloggad_anvandare):
    """Samma adress som en vanlig samling, men en annan sida."""
    bundle_id = _samling(inloggad_anvandare["id"])
    _post(bundle_id)

    svar = client.get(f"/mina-samlingar/{bundle_id}")

    assert svar.status_code == 200
    assert "Ny Swish-kod" in svar.text
    assert "Swish-nummer" in svar.text


def test_annans_samling_ger_404(client, inloggad_anvandare):
    bundle_id = _samling(_annan_anvandare())

    assert client.get(f"/mina-samlingar/{bundle_id}").status_code == 404


def test_utloggad_skickas_till_login(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"])
    client.cookies.clear()

    svar = client.get(f"/mina-samlingar/{bundle_id}")

    assert svar.status_code in (302, 303, 307)
    assert "/login" in svar.headers["location"]


def test_agaren_kan_lagga_till_ett_andamal(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"])
    token = _csrf(client, f"/mina-samlingar/{bundle_id}")

    svar = client.post(
        f"/mina-samlingar/{bundle_id}/swish-poster",
        data={
            "title": "Dagens kollekt",
            "mottagare": "070-123 45 67",
            "belopp": "",
            "meddelande": "Kollekt",
            "fritt_belopp": "1",
            "csrf_token": token,
        },
    )

    assert svar.status_code == 303
    with get_db() as db:
        rad = db.execute("SELECT * FROM swish_items WHERE bundle_id=?", (bundle_id,)).fetchone()
    assert rad["title"] == "Dagens kollekt"
    # Sparas normaliserat, inte som det skrevs in.
    assert rad["mottagare"] == "0701234567"
    assert rad["belopp"] is None


def test_tomt_belopp_utan_fritt_belopp_avvisas(client, inloggad_anvandare):
    """En kod med låst tom summa går inte att betala. Felet ska mötas här,
    inte på anslagstavlan."""
    bundle_id = _samling(inloggad_anvandare["id"])
    token = _csrf(client, f"/mina-samlingar/{bundle_id}")

    svar = client.post(
        f"/mina-samlingar/{bundle_id}/swish-poster",
        data={
            "title": "Diakoni",
            "mottagare": MOTTAGARE,
            "belopp": "",
            "csrf_token": token,
        },
    )

    assert svar.status_code == 303
    assert "swish_error" in svar.headers["location"]
    with get_db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM swish_items", ()).fetchone()["n"] == 0


def test_ogiltigt_nummer_avvisas(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"])
    token = _csrf(client, f"/mina-samlingar/{bundle_id}")

    svar = client.post(
        f"/mina-samlingar/{bundle_id}/swish-poster",
        data={"title": "Diakoni", "mottagare": "123", "belopp": "50", "csrf_token": token},
    )

    assert svar.status_code == 303
    assert "swish_error" in svar.headers["location"]


def test_utan_csrf_nekas(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"])

    svar = client.post(
        f"/mina-samlingar/{bundle_id}/swish-poster",
        data={"title": "Diakoni", "mottagare": MOTTAGARE, "belopp": "50", "csrf_token": "fel"},
    )

    assert svar.status_code == 403


def test_annans_samling_kan_inte_fyllas_pa(client, inloggad_anvandare):
    egen = _samling(inloggad_anvandare["id"], code="egen")
    annans = _samling(_annan_anvandare(), code="annans")
    token = _csrf(client, f"/mina-samlingar/{egen}")

    svar = client.post(
        f"/mina-samlingar/{annans}/swish-poster",
        data={"title": "Kapad", "mottagare": MOTTAGARE, "belopp": "50", "csrf_token": token},
    )

    assert svar.status_code == 404
    with get_db() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) AS n FROM swish_items WHERE bundle_id=?", (annans,)
            ).fetchone()["n"]
            == 0
        )


def test_agaren_kan_andra_kollektandamalet(client, inloggad_anvandare):
    """Veckans skäl till att samlingen finns: ändamålet byts, lappen sitter kvar."""
    bundle_id = _samling(inloggad_anvandare["id"])
    item_id = _post(bundle_id, "Förra veckans ändamål")
    token = _csrf(client, f"/mina-samlingar/{bundle_id}")

    svar = client.post(
        f"/mina-samlingar/{bundle_id}/swish-poster/{item_id}/update",
        data={
            "title": "Dagens kollekt: Act Svenska kyrkan",
            "mottagare": MOTTAGARE,
            "belopp": "150,50",
            "meddelande": "Kollekt",
            "csrf_token": token,
        },
    )

    assert svar.status_code == 303
    with get_db() as db:
        rad = db.execute("SELECT * FROM swish_items WHERE id=?", (item_id,)).fetchone()
    assert rad["title"] == "Dagens kollekt: Act Svenska kyrkan"
    assert rad["belopp"] == "150,50"


def test_annans_post_kan_inte_andras(client, inloggad_anvandare):
    egen = _samling(inloggad_anvandare["id"], code="egen")
    annans = _samling(_annan_anvandare(), code="annans")
    item_id = _post(annans, "Diakoni")
    token = _csrf(client, f"/mina-samlingar/{egen}")

    svar = client.post(
        f"/mina-samlingar/{annans}/swish-poster/{item_id}/update",
        data={"title": "Kapad", "mottagare": MOTTAGARE, "belopp": "50", "csrf_token": token},
    )

    assert svar.status_code == 404
    with get_db() as db:
        assert (
            db.execute("SELECT title FROM swish_items WHERE id=?", (item_id,)).fetchone()["title"]
            == "Diakoni"
        )


def test_post_ur_annan_samling_kan_inte_andras_via_egen(client, inloggad_anvandare):
    """Samlingen är min, posten är inte det. Rätt ägare räcker inte."""
    egen = _samling(inloggad_anvandare["id"], code="egen")
    annans = _samling(inloggad_anvandare["id"], code="annan-egen")
    item_id = _post(annans, "Diakoni")
    token = _csrf(client, f"/mina-samlingar/{egen}")

    svar = client.post(
        f"/mina-samlingar/{egen}/swish-poster/{item_id}/update",
        data={"title": "Fel", "mottagare": MOTTAGARE, "belopp": "50", "csrf_token": token},
    )

    assert svar.status_code == 404


def test_agaren_kan_ta_bort_ett_andamal(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"])
    item_id = _post(bundle_id)
    token = _csrf(client, f"/mina-samlingar/{bundle_id}")

    svar = client.post(
        f"/mina-samlingar/{bundle_id}/swish-poster/{item_id}/delete",
        data={"csrf_token": token},
    )

    assert svar.status_code == 303
    with get_db() as db:
        assert (
            db.execute("SELECT COUNT(*) AS n FROM swish_items WHERE id=?", (item_id,)).fetchone()[
                "n"
            ]
            == 0
        )


def test_ordningen_gar_att_flytta(client, inloggad_anvandare):
    """Ordningen syns på en tryckt lapp."""
    bundle_id = _samling(inloggad_anvandare["id"])
    forst = _post(bundle_id, "Diakoni", sort_order=1)
    sist = _post(bundle_id, "Musik", sort_order=2)
    token = _csrf(client, f"/mina-samlingar/{bundle_id}")

    svar = client.post(
        f"/mina-samlingar/{bundle_id}/swish-poster/{sist}/move",
        data={"riktning": "upp", "csrf_token": token},
    )

    assert svar.status_code == 303
    with get_db() as db:
        ordning = [
            r["id"]
            for r in db.execute(
                "SELECT id FROM swish_items WHERE bundle_id=? ORDER BY sort_order, id",
                (bundle_id,),
            ).fetchall()
        ]
    assert ordning == [sist, forst]


@pytest.mark.parametrize("andelse", ["png", "svg"])
def test_agaren_far_hamta_postens_egen_kod(client, inloggad_anvandare, andelse):
    bundle_id = _samling(inloggad_anvandare["id"])
    item_id = _post(bundle_id, "Diakoni", belopp="100,00")

    svar = client.get(f"/mina-samlingar/{bundle_id}/swish-poster/{item_id}/qr.{andelse}")

    assert svar.status_code == 200
    assert "attachment" in svar.headers["content-disposition"]


def test_lasraden_visas_for_agaren_men_inte_for_besokaren(client, inloggad_anvandare):
    """Ägaren väljer låsen och ska se vad de ger. Besökaren ska betala."""
    bundle_id = _samling(inloggad_anvandare["id"])
    _post(bundle_id, "Dagens kollekt", belopp=None)

    agarvy = client.get(f"/mina-samlingar/{bundle_id}").text
    publikt = client.get("/domkyrkan").text

    assert "Betalaren kan ändra" in agarvy
    assert "även utan kryssrutan" in agarvy
    assert "Betalaren kan ändra" not in publikt


def test_last_post_sager_att_allt_ar_last(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"])
    _post(bundle_id, "Diakoni", belopp="100,00")

    text = client.get(f"/mina-samlingar/{bundle_id}").text
    assert "Allt är låst" in text
    assert "även utan kryssrutan" not in text


def test_trycken_visas_for_agaren(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"])
    item_id = _post(bundle_id)
    client.post(f"/swish-post/{item_id}/tryck")

    assert "1 tryck" in client.get(f"/mina-samlingar/{bundle_id}").text


# --- skapandet -----------------------------------------------------------


def test_swishsamling_skapas_fran_bestallningen(client, inloggad_anvandare, hamta_csrf_token):
    token = hamta_csrf_token(client, "/bestall")

    svar = client.post(
        "/mina-samlingar",
        data={"name": "Ge en gåva", "code": "gava", "theme": "swish", "csrf_token": token},
    )

    assert svar.status_code == 303
    with get_db() as db:
        rad = db.execute("SELECT theme FROM bundles WHERE code='gava'").fetchone()
    assert rad["theme"] == "swish"


def test_okant_tema_faller_tillbaka_pa_rich(client, inloggad_anvandare, hamta_csrf_token):
    token = hamta_csrf_token(client, "/bestall")

    client.post(
        "/mina-samlingar",
        data={"name": "Test", "code": "test", "theme": "hittepa", "csrf_token": token},
    )

    with get_db() as db:
        assert (
            db.execute("SELECT theme FROM bundles WHERE code='test'").fetchone()["theme"] == "rich"
        )


# --- admin och överlåtelse ------------------------------------------------


def test_admin_far_inte_bryta_swishtemat(client, admin, hamta_csrf_token):
    """Ett tema-val som saknar swish skickar 'rich' och slår tyst ut alla
    betalkoder. Samlingen finns kvar men visar ingenting."""
    bundle_id = _samling(admin["id"])
    _post(bundle_id)
    token = hamta_csrf_token(client, f"/admin/bundles/{bundle_id}")

    svar = client.post(
        f"/admin/bundles/{bundle_id}/update",
        data={"name": "Ge en gåva", "theme": "swish", "csrf_token": token},
    )

    assert svar.status_code == 303
    with get_db() as db:
        assert (
            db.execute("SELECT theme FROM bundles WHERE id=?", (bundle_id,)).fetchone()["theme"]
            == "swish"
        )
    assert "Diakoni" in client.get("/domkyrkan").text


def test_admins_temaval_bar_swish(client, admin):
    bundle_id = _samling(admin["id"])

    text = client.get(f"/admin/bundles/{bundle_id}").text

    assert '<option value="swish"' in text


def test_betalkoderna_foljer_med_vid_overlatelse(client, inloggad_anvandare):
    """Överlåtelsen flyttar samlingen. Betalkoderna sitter på samlingen och
    ska följa med oförändrade - ett Swish-nummer får aldrig bytas i en
    ägarflytt."""
    from app.ownership import move_twin_rows

    bundle_id = _samling(inloggad_anvandare["id"])
    item_id = _post(bundle_id, "Diakoni", belopp="100,00")
    ny_agare = _annan_anvandare()

    with get_db() as db:
        move_twin_rows(db, "domkyrkan", inloggad_anvandare["id"], ny_agare)
        bundle = db.execute("SELECT owner_id FROM bundles WHERE id=?", (bundle_id,)).fetchone()
        post = db.execute("SELECT * FROM swish_items WHERE id=?", (item_id,)).fetchone()

    assert bundle["owner_id"] == ny_agare
    assert post["bundle_id"] == bundle_id
    assert post["mottagare"] == MOTTAGARE
    assert post["belopp"] == "100,00"

    # Den gamla ägaren når inte längre redigeringsvyn.
    assert client.get(f"/mina-samlingar/{bundle_id}").status_code == 404


# --- en rad som inte går att koda -----------------------------------------


def _trasig_post(bundle_id: int) -> int:
    """En rad som gränssnittet aldrig skulle skriva.

    Allt som skapas via routerna går genom _falt() och normaliseras, så det
    här är en rad någon ändrat direkt i databasen. Den ska inte fälla en
    anslagstavla.
    """
    with get_db() as db:
        db.execute(
            """INSERT INTO swish_items
               (bundle_id, title, mottagare, belopp, meddelande,
                fri_mottagare, fritt_belopp, fritt_meddelande, sort_order)
               VALUES (?,?,?,?,?,0,0,0,9)""",
            (bundle_id, "Trasig", "123", "100,00", "Trasig"),
        )
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_okodbar_post_faller_inte_samlingssidan(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"])
    _post(bundle_id, "Diakoni", belopp="100,00")
    _trasig_post(bundle_id)

    svar = client.get("/domkyrkan")

    assert svar.status_code == 200
    assert "Diakoni" in svar.text
    assert "Trasig" not in svar.text


def test_agaren_ser_vilken_post_som_ar_trasig(client, inloggad_anvandare):
    """Utelämnad publikt, men synlig för den som kan rätta den."""
    bundle_id = _samling(inloggad_anvandare["id"])
    item_id = _trasig_post(bundle_id)

    text = client.get(f"/mina-samlingar/{bundle_id}").text

    assert "Trasig" in text
    assert "går inte att koda" in text
    assert str(item_id) in text


def test_okodbar_posts_bild_ger_404_inte_500(client, inloggad_anvandare):
    item_id = _trasig_post(_samling(inloggad_anvandare["id"]))

    assert client.get(f"/swish-post/{item_id}/qr.png").status_code == 404


# --- samlingens egen QR-kod -----------------------------------------------


def test_swishvyn_har_samma_qr_ruta_som_vanliga_samlingar(client, inloggad_anvandare):
    """Samlingsvyn delades i två mallar 2026-09-08, och QR-rutan följde inte
    med till swish-halvan. Routerna var gemensamma hela tiden - det var bara
    mallen som blev tunnare, och det syns inte förrän någon letar efter
    knappen.
    """
    bundle_id = _samling(inloggad_anvandare["id"])

    text = client.get(f"/mina-samlingar/{bundle_id}").text

    # qr.js hänger på de här kroknamnen.
    assert f'data-qr-open="qr-bundle-{bundle_id}"' in text
    assert "data-qr-val" in text
    assert text.count("data-qr-lank") == 2
    assert f"/mina-samlingar/{bundle_id}/qr.zip" in text
    assert '<script src="/static/qr.js">' in text


def test_symbolvalen_finns_i_swishvyn(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"])

    text = client.get(f"/mina-samlingar/{bundle_id}").text

    for varde in ("skold-svart", "skold-farg"):
        assert f'value="{varde}"' in text, varde


@pytest.mark.parametrize("andelse", ["png", "svg", "zip"])
def test_samlingens_egen_kod_gar_att_hamta(client, inloggad_anvandare, andelse):
    """Routen gäller alla samlingar oavsett tema - provet ser till att den
    fortsätter göra det."""
    bundle_id = _samling(inloggad_anvandare["id"])

    svar = client.get(f"/mina-samlingar/{bundle_id}/qr.{andelse}")

    assert svar.status_code == 200


def test_samlingens_kod_bar_kortlanken_inte_en_betalning(client, inloggad_anvandare):
    """Två sorters koder lever på samma sida. Den här bär adressen till
    sidan med alla Swish-koder, postens egen bär en enskild Swish-kod."""
    from app import qr

    bundle_id = _samling(inloggad_anvandare["id"])
    _post(bundle_id, "Diakoni", belopp="100,00")

    samlingen = _zxing(client.get(f"/mina-samlingar/{bundle_id}/qr.png").content)
    posten = _zxing(
        client.get(
            f"/mina-samlingar/{bundle_id}/swish-poster/"
            f"{_post(bundle_id, 'Musik', belopp='150,00')}/qr.png"
        ).content
    )

    assert samlingen == qr.lankadress("domkyrkan")
    assert posten.startswith(f"C{MOTTAGARE};150,00;")


# --- felet ska stå vid rätt formulär --------------------------------------


def test_felet_pekar_ut_posten_det_galler(client, inloggad_anvandare):
    """Utan JavaScript kommer felet tillbaka som query-parameter. Då ska det
    stå vid den post som avvisades, inte som en banner högst upp - med tre
    koder i listan hamnar man annars långt från fältet man skrev fel i.
    """
    bundle_id = _samling(inloggad_anvandare["id"])
    item_id = _post(bundle_id, "Diakoni", belopp="100,00")
    token = _csrf(client, f"/mina-samlingar/{bundle_id}")

    svar = client.post(
        f"/mina-samlingar/{bundle_id}/swish-poster/{item_id}/update",
        data={"title": "Diakoni", "mottagare": MOTTAGARE, "belopp": "", "csrf_token": token},
    )

    assert svar.status_code == 303
    plats = svar.headers["location"]
    assert "swish_error=" in plats
    assert f"fel_post={item_id}" in plats


def test_fel_utan_utpekad_post_hor_till_nya_formularet(client, inloggad_anvandare):
    bundle_id = _samling(inloggad_anvandare["id"])
    token = _csrf(client, f"/mina-samlingar/{bundle_id}")

    svar = client.post(
        f"/mina-samlingar/{bundle_id}/swish-poster",
        data={"title": "Ny", "mottagare": MOTTAGARE, "belopp": "", "csrf_token": token},
    )

    assert "swish_error=" in svar.headers["location"]
    assert "fel_post=" not in svar.headers["location"]


def test_felrutan_star_vid_posten_och_inte_hogst_upp(client, inloggad_anvandare):
    """Bannern högst upp är borttagen. Provet faller om den kommer tillbaka."""
    bundle_id = _samling(inloggad_anvandare["id"])
    item_id = _post(bundle_id, "Diakoni", belopp="100,00")

    text = client.get(
        f"/mina-samlingar/{bundle_id}?swish_error=Det+gick+fel&fel_post={item_id}"
    ).text

    assert 'class="alert alert-error"' not in text
    # Felet ska ligga inne i postens eget formulär.
    formular = text.split(f'id="uppd-{item_id}"')[1].split("</form>")[0]
    assert "Det gick fel" in formular


def test_valideringen_frager_servern_och_sparrar_knappen(client, inloggad_anvandare):
    """Sidan får aldrig bedöma en betalning själv - då finns reglerna på två
    ställen. Den frågar /swish-data, samma väg som generatorn."""
    bundle_id = _samling(inloggad_anvandare["id"])

    text = client.get(f"/mina-samlingar/{bundle_id}").text

    assert "/swish-data?" in text
    assert "spara.disabled" in text
