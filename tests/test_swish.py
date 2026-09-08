"""Swish-betallänkar: QR-strängen och applänken.

Proven mäter mot specens egna exempel där sådana finns. Formaten är inte
våra, och en avvikelse upptäcks annars först när någon står vid en
anslagstavla och Swish-appen vägrar.

Källa: docs/swish-qr.md, som i sin tur bygger på Swish "Guide Swish QR code
design specification" v1.7.2 avsnitt 6.1.
"""

import json
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from app.swish import (
    MAX_MEDDELANDE,
    Swishbetalning,
    Swishfel,
    applank,
    qr_strang,
)


def test_specens_eget_exempel():
    """Det enda facit vi har utifrån. Ändras den här raden är formatet fel."""
    betalning = Swishbetalning(
        mottagare="1237856901", belopp="100", meddelande="12229445"
    )

    assert qr_strang(betalning) == "C1237856901;100,00;12229445;0"


def test_beloppet_far_tva_decimaler_och_komma():
    """Swish vill ha 100,00 och inte 100. Punkt läses som något annat."""
    assert ";100,00;" in qr_strang(Swishbetalning("1231234567", "100"))
    assert ";99,50;" in qr_strang(Swishbetalning("1231234567", "99.5"))
    assert ";99,50;" in qr_strang(Swishbetalning("1231234567", "99,5"))


def test_tomma_falt_behalls_som_tomma_stringar():
    """En gåva är C<nummer>;;;<mask>. Fälten försvinner inte, de blir tomma."""
    gava = Swishbetalning(
        "1231234567", redigerbart_belopp=True, redigerbart_meddelande=True
    )

    assert qr_strang(gava) == "C1231234567;;;6"


@pytest.mark.parametrize(
    "falt,vantad",
    [
        ({}, 0),
        ({"redigerbar_mottagare": True}, 1),
        ({"redigerbart_belopp": True}, 2),
        ({"redigerbart_meddelande": True}, 4),
        ({"redigerbart_belopp": True, "redigerbart_meddelande": True}, 6),
        (
            {
                "redigerbar_mottagare": True,
                "redigerbart_belopp": True,
                "redigerbart_meddelande": True,
            },
            7,
        ),
    ],
)
def test_masken_raknas_ur_kryssrutorna(falt, vantad):
    """Bit satt betyder REDIGERBAR, tvärtom mot vad namnet lock_mask antyder.

    Slöjda har alltid 7. Här väljer beställaren per fält, så masken måste
    räknas fram och inte hårdkodas.
    """
    betalning = Swishbetalning("1231234567", belopp="50", **falt)

    assert qr_strang(betalning).rsplit(";", 1)[1] == str(vantad)


def test_meddelandet_ar_url_kodat():
    """Mellanslag blir %20, inte plus, och svenska tecken överlever."""
    betalning = Swishbetalning(
        "1231234567", "100", "Kollekt Härnösands domkyrka"
    )

    strang = qr_strang(betalning)

    assert "Kollekt%20H%C3%A4rn%C3%B6sands%20domkyrka" in strang
    assert unquote(strang.split(";")[2]) == "Kollekt Härnösands domkyrka"


def test_meddelandet_kapas_vid_femtio():
    """Schemat säger 70 tecken, men appen visar och sparar bara 50. Den
    snävare gränsen är den användaren möter."""
    betalning = Swishbetalning("1231234567", "100", "a" * 80)

    assert len(unquote(qr_strang(betalning).split(";")[2])) == MAX_MEDDELANDE


def test_numret_maste_vara_tio_siffror():
    for fel in ("123", "12312345678", "", "abcdefghij"):
        with pytest.raises(Swishfel):
            qr_strang(Swishbetalning(fel, "100"))


def test_mellanslag_i_numret_stors_bort():
    """Ett nummer klistras ofta in med mellanslag eller bindestreck."""
    assert qr_strang(Swishbetalning("123 123 45 67", "100")).startswith("C1231234567;")


def test_last_tomt_belopp_avvisas():
    """En kod utan belopp som betalaren inte får fylla i går inte att betala.

    Felet ska mötas i beställningen. En tryckt kod går inte att rätta.
    """
    with pytest.raises(Swishfel):
        qr_strang(Swishbetalning("1231234567"))


@pytest.mark.parametrize("belopp", ["0", "-5", "abc", "1000000"])
def test_omojliga_belopp_avvisas(belopp):
    with pytest.raises(Swishfel):
        qr_strang(Swishbetalning("1231234567", belopp))


# --------------------------------------------------------------------------
# Applänken
# --------------------------------------------------------------------------


def _data(lank: str) -> dict:
    fraga = parse_qs(urlparse(lank).query)
    return json.loads(fraga["data"][0])


def test_applanken_bar_versionen_som_strang():
    data = _data(applank(Swishbetalning("1231234567", "100")))

    assert data["version"] == "1.0"
    assert isinstance(data["version"], str)


def test_beloppet_ar_hela_kronor_som_strang():
    """Applänken vill ha 100 där QR-strängen vill ha 100,00. Två format för
    samma summa, och att blanda ihop dem ger en app som öppnar tom."""
    data = _data(applank(Swishbetalning("1231234567", "100.00")))

    assert data["amount"]["value"] == "100"
    assert isinstance(data["amount"]["value"], str)


def test_editable_satts_bara_som_true():
    """Det finns ingen editable: false. Nyckeln utelämnas för låsta fält."""
    lank = applank(
        Swishbetalning("1231234567", "100", "Kollekt", redigerbart_belopp=True)
    )

    data = _data(lank)
    assert data["amount"]["editable"] is True
    assert "editable" not in data["payee"]
    assert "editable" not in data["message"]


def test_tomma_falt_utelamnas_helt():
    data = _data(applank(Swishbetalning("1231234567", "100")))

    assert "message" not in data
    assert set(data) == {"version", "payee", "amount"}


def test_gava_utan_belopp_ger_ingen_applank():
    """Det svaga stället i formatet, och skälet till att funktionen får
    returnera None.

    En gåva har tomt belopp som betalaren ska fylla i. Nyckeln amount
    utelämnas när värdet saknas, och då finns ingenstans att sätta editable.
    QR-koden klarar samma fall med tom sträng och satt bit.
    """
    gava = Swishbetalning("1231234567", redigerbart_belopp=True)

    assert applank(gava) is None
    assert qr_strang(gava) == "C1231234567;;;2"


def test_applanken_ar_url_kodad():
    """JSON i en frågesträng. Ett okodat citattecken bryter länken."""
    lank = applank(Swishbetalning("1231234567", "100", "Kollekt & kaffe"))

    assert lank.startswith("swish://payment?data=")
    assert '"' not in lank
    assert _data(lank)["message"]["value"] == "Kollekt & kaffe"


# --------------------------------------------------------------------------
# Ritningen
# --------------------------------------------------------------------------


def _zxing(png: bytes) -> str | None:
    import io

    import zxingcpp
    from PIL import Image

    traff = zxingcpp.read_barcode(Image.open(io.BytesIO(png)).convert("RGB"))
    return traff.text if traff else None


def test_swishkoden_avkodas_med_symbolen():
    """Symbolen täcker mitten, så koden ritas med H. En kod som ser rätt ut
    men inte går att läsa är det enda utfall som betyder något här."""
    from app import qr

    strang = qr_strang(Swishbetalning("1231234567", "100", "Kollekt"))

    assert _zxing(qr.png(strang, symbol_installning=qr.SWISH)) == strang


def test_swishsymbolen_ar_tjugofem_procent():
    """Swish eget krav, inte vårt val. Sköldarnas 30 gäller inte här."""
    from app import qr

    assert qr.SWISH.andel == 0.25


def test_swishsymbolen_gar_inte_att_valja_for_en_kortlank():
    """Symbolen hör till en betalkod. Kan den väljas via frågesträngen får en
    vanlig kortlänk Swish-logotypen mitt i, vilket säger fel sak."""
    from app import qr

    assert "swish" not in qr.SYMBOLER
    assert qr.valj_symbol("swish") is None


def test_ingen_frans_runt_swishsymbolen():
    """Swish-filen bär SVART under de genomskinliga pixlarna, och en rak
    LANCZOS-skalning blandar in svärtan i kantpixlarna.

    Provet mäter den vita ringen strax utanför symbolen: en frans gör den
    märkbart mörkare än rent vitt.
    """
    import io

    from PIL import Image

    from app import qr

    strang = qr_strang(Swishbetalning("1231234567", "100"))
    bild = Image.open(io.BytesIO(qr.png(strang, symbol_installning=qr.SWISH))).convert("RGB")

    # Symbolens ytterkant, mätt på mitthöjd strax till vänster om logotypen.
    mitt = bild.width // 2
    halva = int(bild.width * qr.SWISH.andel / 2)
    for avstand in range(2, 6):
        pixel = bild.getpixel((mitt - halva + avstand, mitt))
        assert min(pixel) > 200, f"mörk frans vid {avstand} px in: {pixel}"


# --------------------------------------------------------------------------
# Catch-all-routen: den farligaste ändringen i hela tasken
# --------------------------------------------------------------------------
#
# GET /<kod> gör i dag en sak: 302 till target_url. En Swish-länk ska i
# stället rendera en sida. Provet nedan skrivs FÖRE den grenen läggs in, och
# är det som säger till om vanliga kortlänkar slutar fungera.


def test_vanlig_kortlank_omdirigerar_fortfarande(client):
    """Varje kortlänk i drift går genom den här routen.

    Provet finns för att skydda dem när Swish-grenen läggs in. Faller det har
    tjänstens huvudfunktion gått sönder, inte en ny funktion.
    """
    from app.database import get_db

    with get_db() as db:
        db.execute("INSERT INTO users (email) VALUES ('n@svenskakyrkan.se')")
        agare = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute(
            "INSERT INTO links (code, target_url, owner_id, status) VALUES "
            "('vanlig', 'https://www.svenskakyrkan.se/harnosand', ?, 1)",
            (agare,),
        )

    svar = client.get("/vanlig")

    assert svar.status_code == 302
    assert svar.headers["location"] == "https://www.svenskakyrkan.se/harnosand"


def test_klick_raknas_for_vanlig_lank(client):
    """302:an ÄR klicket i dagens modell. Swish-länken får en egen räkning,
    men den här betydelsen ska stå kvar."""
    from app.database import get_db

    with get_db() as db:
        db.execute("INSERT INTO users (email) VALUES ('n@svenskakyrkan.se')")
        agare = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute(
            "INSERT INTO links (code, target_url, owner_id, status) VALUES "
            "('raknas', 'https://www.svenskakyrkan.se/x', ?, 1)",
            (agare,),
        )

    client.get("/raknas")

    with get_db() as db:
        antal = db.execute(
            "SELECT count(*) FROM clicks c JOIN links l ON l.id = c.link_id "
            "WHERE l.code = 'raknas'"
        ).fetchone()[0]
    assert antal == 1


# --------------------------------------------------------------------------
# Landningssidan och klickräkningen
# --------------------------------------------------------------------------


def _swishlank(client, code="kollekt", **falt):
    """Lägger en Swish-länk och returnerar dess id."""
    from app.database import get_db

    rad = {
        "swish_mottagare": "1231234567",
        "swish_belopp": "100",
        "swish_meddelande": "Kollekt",
        "swish_mask": 2,
    }
    rad.update(falt)
    with get_db() as db:
        db.execute("INSERT OR IGNORE INTO users (email) VALUES ('a@svenskakyrkan.se')")
        agare = db.execute(
            "SELECT id FROM users WHERE email='a@svenskakyrkan.se'"
        ).fetchone()[0]
        db.execute(
            """INSERT INTO links
               (code, target_url, owner_id, status, typ, swish_mottagare,
                swish_belopp, swish_meddelande, swish_mask)
               VALUES (?, ?, ?, 1, 'swish', ?, ?, ?, ?)""",
            (
                code,
                f"https://svky.se/{code}",
                agare,
                rad["swish_mottagare"],
                rad["swish_belopp"],
                rad["swish_meddelande"],
                rad["swish_mask"],
            ),
        )
        return db.execute("SELECT id FROM links WHERE code=?", (code,)).fetchone()[0]


def test_swishlank_renderar_i_stallet_for_att_omdirigera(client):
    """Den gren som gör hela tasken riskabel. Vanliga länkar 302:ar
    fortfarande, se provet längre upp."""
    _swishlank(client)

    svar = client.get("/kollekt")

    assert svar.status_code == 200
    assert "Betala med Swish" in svar.text
    assert "100 kr" in svar.text


def test_sidvisningen_ar_inte_ett_klick(client):
    """Beslutet i TASK-1676: sidvisningen loggas i page_views, trycket på
    Öppna Swish som ett klick. Räknas visningen som klick blir siffran
    uppblåst - ett skannat anslag ger en visning utan avsikt att betala."""
    from app.database import get_db

    lank = _swishlank(client)

    client.get("/kollekt")

    with get_db() as db:
        klick = db.execute("SELECT count(*) FROM clicks WHERE link_id=?", (lank,)).fetchone()[0]
        visningar = db.execute(
            "SELECT count(*) FROM page_views WHERE path='/kollekt'"
        ).fetchone()[0]
    assert klick == 0
    assert visningar == 1


def test_oppna_raknar_ett_klick_och_skickar_till_appen(client):
    from app.database import get_db

    lank = _swishlank(client)

    svar = client.get("/kollekt/oppna")

    assert svar.status_code == 303
    assert svar.headers["location"].startswith("swish://payment?data=")
    with get_db() as db:
        assert db.execute(
            "SELECT count(*) FROM clicks WHERE link_id=?", (lank,)
        ).fetchone()[0] == 1


def test_gava_utan_belopp_skickar_tillbaka_till_sidan(client):
    """Applänken kan inte uttrycka en gåva med fritt belopp. Knappen visas
    inte, men routen ska ändå inte leda till ingenting."""
    _swishlank(client, code="gava", swish_belopp=None, swish_mask=2)

    sida = client.get("/gava")
    assert sida.status_code == 200
    assert "Öppna Swish" not in sida.text
    assert "Du väljer själv" in sida.text

    svar = client.get("/gava/oppna")
    assert svar.status_code == 303
    assert svar.headers["location"] == "/gava"


def test_qr_koden_bar_betalstrangen_inte_kortlanken(client):
    """Koden på landningssidan ska starta en betalning, inte leda tillbaka
    till sidan den står på."""
    _swishlank(client)

    svar = client.get("/kollekt/swish-qr.png")

    assert svar.status_code == 200
    assert svar.headers["content-type"] == "image/png"
    assert _zxing(svar.content) == "C1231234567;100,00;Kollekt;2"


def test_swishkoden_ar_publik(client):
    """Landningssidan är publik, alltså måste bilden på den vara det."""
    assert client.get("/kollekt/swish-qr.png").status_code in (200, 404)


def test_avaktiverad_swishlank_ger_404(client):
    from app.database import get_db

    _swishlank(client, code="stangd")
    with get_db() as db:
        db.execute("UPDATE links SET status=3 WHERE code='stangd'")

    assert client.get("/stangd").status_code == 404
    assert client.get("/stangd/oppna").status_code == 404
    assert client.get("/stangd/swish-qr.png").status_code == 404


# --------------------------------------------------------------------------
# Beställningen och ägarvyn
# --------------------------------------------------------------------------


def _skapa_via_formularet(client, hamta_csrf_token, **falt):
    data = {
        "swish_mottagare": "1231234567",
        "swish_belopp": "150",
        "swish_meddelande": "Kollekt",
        "fritt_belopp": "1",
        "code": "provkod",
        "note": "",
        "csrf_token": hamta_csrf_token(client, "/bestall"),
    }
    data.update(falt)
    return client.post("/bestall/swish", data={k: v for k, v in data.items() if v is not None})


def test_utloggad_kan_inte_skapa_swishlank(client):
    """En Swish-kod pekar ut ett betalmottagarnummer. Det ska gå att fråga
    någon om i efterhand."""
    svar = client.post(
        "/bestall/swish",
        data={"swish_mottagare": "1231234567", "swish_belopp": "10", "csrf_token": "x"},
    )

    assert svar.status_code in (303, 403)


def test_utan_giltig_csrf_skapas_ingenting(client, inloggad_anvandare):
    from app.database import get_db

    svar = client.post(
        "/bestall/swish",
        data={"swish_mottagare": "1231234567", "swish_belopp": "10", "csrf_token": "fel"},
    )

    assert svar.status_code == 403
    with get_db() as db:
        assert db.execute("SELECT count(*) FROM links WHERE typ='swish'").fetchone()[0] == 0


def test_inloggad_skapar_swishlank(client, inloggad_anvandare, hamta_csrf_token):
    from app.database import get_db

    svar = _skapa_via_formularet(client, hamta_csrf_token)

    assert svar.status_code == 303
    assert "skapad=provkod" in svar.headers["location"]
    with get_db() as db:
        rad = db.execute("SELECT * FROM links WHERE code='provkod'").fetchone()
    assert rad["typ"] == "swish"
    assert rad["swish_mottagare"] == "1231234567"
    assert rad["swish_mask"] == 2  # bara beloppet fritt
    # target_url bär sidans egen adress: kolumnen är NOT NULL, och en rad som
    # av misstag renderas som vanlig länk ska leda rätt.
    assert rad["target_url"].endswith("/provkod")


def test_last_tomt_belopp_avvisas_i_formularet(client, inloggad_anvandare, hamta_csrf_token):
    """Kodningen ÄR valideringen. En kod som inte går att betala ska mötas
    här och inte på anslagstavlan."""
    from app.database import get_db

    svar = _skapa_via_formularet(client, hamta_csrf_token, swish_belopp="", fritt_belopp=None)

    assert svar.status_code == 400
    with get_db() as db:
        assert db.execute("SELECT count(*) FROM links WHERE typ='swish'").fetchone()[0] == 0


def test_upptagen_kod_avvisas(client, inloggad_anvandare, hamta_csrf_token):
    from app.database import get_db

    with get_db() as db:
        db.execute(
            "INSERT INTO links (code, target_url, owner_id, status) "
            "VALUES ('provkod', 'https://x', ?, 1)",
            (inloggad_anvandare["id"],),
        )

    svar = _skapa_via_formularet(client, hamta_csrf_token)

    assert svar.status_code == 400
    with get_db() as db:
        assert db.execute("SELECT count(*) FROM links WHERE typ='swish'").fetchone()[0] == 0


def test_agarvyn_visar_betalningen_och_applanken(client, inloggad_anvandare, hamta_csrf_token):
    _skapa_via_formularet(client, hamta_csrf_token)

    text = client.get("/mina-lankar").text

    assert "150 kr" in text
    assert "Kollekt" in text
    # data-applank och inte klassnamnet: skriptet i mallen bär selektorn
    # ".kopiera-applank" i sin text, och ett prov som letar efter den mäter
    # att JavaScript finns - inte att knappen ritas.
    assert 'data-applank="swish://payment?data=' in text


def test_gava_visar_ingen_kopieraknapp(client, inloggad_anvandare, hamta_csrf_token):
    """Applänken kan inte uttrycka fritt belopp. En knapp som kopierar
    ingenting är sämre än ingen knapp."""
    _skapa_via_formularet(
        client, hamta_csrf_token, code="gavokod", swish_belopp="", fritt_belopp="1"
    )

    text = client.get("/mina-lankar").text

    assert "Fritt belopp" in text
    assert "data-applank=" not in text
    assert "kan inte uttrycka det" in text
