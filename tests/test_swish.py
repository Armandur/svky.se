"""Swish-betallänkar: QR-strängen och applänken.

Proven mäter mot specens egna exempel där sådana finns. Formaten är inte
våra, och en avvikelse upptäcks annars först när någon står vid en
anslagstavla och Swish-appen vägrar.

Källa: docs/swish-qr.md, som i sin tur bygger på Swish "Guide Swish QR code
design specification" v1.7.2 avsnitt 6.1.
"""

import json
import re
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
    betalning = Swishbetalning(mottagare="1237856901", belopp="100", meddelande="12229445")

    assert qr_strang(betalning) == "C1237856901;100,00;12229445;0"


def test_beloppet_far_tva_decimaler_och_komma():
    """Swish vill ha 100,00 och inte 100. Punkt läses som något annat."""
    assert ";100,00;" in qr_strang(Swishbetalning("1231234567", "100"))
    assert ";99,50;" in qr_strang(Swishbetalning("1231234567", "99.5"))
    assert ";99,50;" in qr_strang(Swishbetalning("1231234567", "99,5"))


def test_tomma_falt_behalls_som_tomma_stringar():
    """En gåva är C<nummer>;;;<mask>. Fälten försvinner inte, de blir tomma."""
    gava = Swishbetalning("1231234567", redigerbart_belopp=True, redigerbart_meddelande=True)

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
    betalning = Swishbetalning("1231234567", "100", "Kollekt Härnösands domkyrka")

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


def test_applanken_bar_versionen_som_tal():
    """version är TALET 1, inte strängen "1.0".

    Uppmätt på telefon 2026-09-08: en länk med strängen öppnar Swish men
    fyller inte i någonting. Det var den ENDA skillnaden mellan en form som
    fungerade och en som inte gjorde det. Vår egen spec påstod motsatsen.
    """
    data = _data(applank(Swishbetalning("1231234567", "100")))

    assert data["version"] == 1
    assert isinstance(data["version"], int)
    assert not isinstance(data["version"], bool)


def test_beloppet_ar_ett_tal_i_applanken():
    """Applänken vill ha talet 100 där QR-strängen vill ha strängen 100,00.
    Två format för samma summa, och att blanda ihop dem ger en app som
    öppnar tom."""
    data = _data(applank(Swishbetalning("1231234567", "100.00")))

    assert data["amount"]["value"] == 100
    assert isinstance(data["amount"]["value"], int | float)


def test_oren_foljer_med_in_i_applanken():
    """Tidigare skickades bara heltalsdelen, så 149,50 blev 149 och femtio
    öre försvann tyst mellan koden och appen."""
    data = _data(applank(Swishbetalning("1231234567", "149,50")))

    assert data["amount"]["value"] == 149.5


def test_editable_satts_bara_som_true():
    """Det finns ingen editable: false. Nyckeln utelämnas för låsta fält."""
    lank = applank(Swishbetalning("1231234567", "100", "Kollekt", redigerbart_belopp=True))

    data = _data(lank)
    assert data["amount"]["editable"] is True
    assert "editable" not in data["payee"]
    assert "editable" not in data["message"]


def test_tomma_falt_utelamnas_helt():
    data = _data(applank(Swishbetalning("1231234567", "100")))

    assert "message" not in data
    assert set(data) == {"version", "payee", "amount"}


def test_gava_utelamnar_amount_helt():
    """En gåva med fritt belopp uttrycks genom att nyckeln SAKNAS.

    Uppmätt på telefon 2026-09-08: tom sträng, noll och null fungerar alla
    sämre eller inte alls. Strängen "0" öppnar visserligen appen, men
    tvingar givaren att ändra från noll med en varning om att en krona är
    minsta belopp.

    Slutsatsen förut var att formatet inte kunde uttrycka en gåva alls, och
    den byggde på en kommentar i slöjdas kod i stället för på en mätning.
    """
    gava = Swishbetalning("1231234567", redigerbart_belopp=True, meddelande="Gåva")

    data = _data(applank(gava))
    assert "amount" not in data
    assert data["message"]["value"] == "Gåva"
    # Meddelandet är URL-kodat i QR-strängen, till skillnad från i applänken.
    assert qr_strang(gava) == "C1231234567;;G%C3%A5va;2"


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
            "SELECT count(*) FROM clicks c JOIN links l ON l.id = c.link_id WHERE l.code = 'raknas'"
        ).fetchone()[0]
    assert antal == 1


# --------------------------------------------------------------------------
# Generatorn på /swish och /swishqr
# --------------------------------------------------------------------------
#
# Ett verktyg, inte en länk. Ingenting sparas, och därför finns ingen
# ägarskapskontroll att prova - i stället provas att frågesträngen räcker.


def test_generatorn_ar_publik_pa_bada_adresserna(client):
    """Båda koderna står i RESERVED_CODES, och folk skriver rimligen det
    ena eller det andra."""
    for vag in ("/swish", "/swishqr"):
        svar = client.get(vag)

        assert svar.status_code == 200, vag
        assert "Skapa en Swish-kod" in svar.text


def _resultatpanel_dold(text: str) -> bool:
    """Sant när resultatpanelen är dold och tomrutan visas.

    Mäts på taggarna, inte på om strängen "swish-kod.png" finns någonstans i
    svaret: adresserna står numera också i sidans JavaScript, som räknar om
    koden medan man skriver. Ett prov som letar efter texten hade fallit på
    manuset i stället för på det den påstår sig mäta.
    """
    fardig = re.search(r'<div id="gen-fardig"([^>]*)>', text)
    tom = re.search(r'<div class="gen-tom" id="gen-tom"([^>]*)>', text)
    assert fardig, "sidan saknar resultatpanelen #gen-fardig"
    assert tom, "sidan saknar tomrutan #gen-tom"
    return "hidden" in fardig.group(1) and "hidden" not in tom.group(1)


def test_tom_generator_visar_inget_resultat(client):
    text = client.get("/swish").text

    assert "Fyll i Swish-numret" in text
    assert _resultatpanel_dold(text)


def test_ifylld_generator_visar_kod_och_lankar(client):
    svar = client.get("/swish?mottagare=1231234567&belopp=150&meddelande=Kollekt&fritt_belopp=1")

    assert svar.status_code == 200
    assert not _resultatpanel_dold(svar.text)
    assert "/swish-kod.png?" in svar.text
    assert "/swish-kod.svg?" in svar.text
    # Betalsträngen visas som text, så det går att kontrollera med ögat.
    assert "C1231234567;150,00;Kollekt;2" in svar.text


def test_ingen_egen_ruta_for_sidans_egen_adress(client):
    """Adressfältet bär redan den länken.

    Ett fält som dubblerar webbläsarens adressrad är brus, och det man vill
    klistra in i ett CMS är bilden eller en betallänk med egen kortkod -
    inte en förifylld generator.
    """
    text = client.get("/swish?mottagare=1231234567&belopp=50").text

    assert "Länk att klistra in" not in text


def test_koden_avkodas_till_betalningen(client):
    svar = client.get("/swish-kod.png?mottagare=1231234567&belopp=150&meddelande=Kollekt")

    assert svar.status_code == 200
    assert svar.headers["content-type"] == "image/png"
    assert _zxing(svar.content) == "C1231234567;150,00;Kollekt;0"


def test_svg_laddas_ner_med_eget_namn(client):
    svar = client.get("/swish-kod.svg?mottagare=1231234567&belopp=150")

    assert svar.status_code == 200
    assert "swish-qr.svg" in svar.headers["content-disposition"]


def test_omojlig_betalning_ger_fel_i_stallet_for_kod(client):
    """Tomt och låst belopp går inte att betala. Felet ska mötas här, inte
    på anslagstavlan."""
    svar = client.get("/swish?mottagare=1231234567")

    assert svar.status_code == 200
    assert _resultatpanel_dold(svar.text)
    assert "belopp" in svar.text.lower()

    assert client.get("/swish-kod.png?mottagare=1231234567").status_code == 404


def test_trasigt_nummer_faller_inte_sidan(client):
    svar = client.get("/swish?mottagare=123")

    assert svar.status_code == 200
    assert "tio siffror" in svar.text.lower()


def test_gava_visar_applank(client):
    svar = client.get("/swish?mottagare=1231234567&fritt_belopp=1")

    assert svar.status_code == 200
    assert "swish-kod.png" in svar.text
    assert "Applänk för mobil" in svar.text


def test_oren_gar_bra_i_bada_formen():
    """Swish tar kronor och ören. Både komma och punkt ska fungera - folk
    skriver det ena eller det andra utan att tänka på det."""
    for skrivet, vantat in (("149,50", "149,50"), ("149.50", "149,50"), ("0,5", "0,50")):
        assert qr_strang(Swishbetalning("1231234567", skrivet)).split(";")[1] == vantat


def test_fler_an_tva_decimaler_avvisas():
    """Tidigare avrundades 10,999 tyst till 11,00. Beställaren fick då en
    tryckt kod på fel belopp utan att veta om det."""
    for belopp in ("10,999", "10.001", "5,1234"):
        with pytest.raises(Swishfel):
            qr_strang(Swishbetalning("1231234567", belopp))


def test_generatorn_upplyser_om_oren(client):
    text = client.get("/swish").text

    assert "ören" in text
    assert "149,50" in text


def test_applanken_gar_att_trycka_pa(client):
    """Att prova betalningen är det man vill göra, och att kopiera länken
    kommer efteråt. Knappen står därför före fältet."""
    text = client.get("/swish?mottagare=1231234567&belopp=150").text

    assert 'href="swish://payment?data=' in text
    assert "Testa i Swish" in text
    # Upplysningen om att det kräver en telefon.
    assert "bara på en telefon" in text


def test_gava_far_ocksa_en_testknapp(client):
    """Kollekt utan förbestämd summa är det vanligaste fallet i en kyrka,
    och det saknade knapp så länge gåvan troddes sakna applänk."""
    text = client.get("/swish?mottagare=1231234567&fritt_belopp=1").text

    assert "Testa i Swish" in text


# --- /swish-data: koden räknas om medan man skriver ----------------------


def test_data_ger_samma_strang_som_sidan(client):
    """Sidan och manuset måste ge samma kod. Går de isär blir det den ena
    som trycks och den andra som testas."""
    fraga = "mottagare=1231234567&belopp=150&meddelande=Kollekt&fritt_belopp=1"

    data = client.get(f"/swish-data?{fraga}").json()

    assert data["lage"] == "ok"
    assert data["kodstrang"] == "C1231234567;150,00;Kollekt;2"
    assert data["kodstrang"] in client.get(f"/swish?{fraga}").text
    assert data["applank"].startswith("swish://payment?data=")


def test_halvskrivet_nummer_ar_tomt_inte_fel(client):
    """Den som skrivit tre siffror skriver fortfarande. Ett felmeddelande
    där är en tillrättavisning mitt i en mening."""
    for siffror in ("1", "123", "123123456"):
        data = client.get(f"/swish-data?mottagare={siffror}").json()

        assert data["lage"] == "tom", siffror
        assert data["fel"] is None, siffror


def test_for_langt_nummer_ar_ett_fel(client):
    """Elva siffror är inte ett halvskrivet nummer, det är ett fel nummer."""
    data = client.get("/swish-data?mottagare=12312345678&belopp=100").json()

    assert data["lage"] == "fel"
    assert "tio siffror" in data["fel"]


def test_felet_pekar_pa_numret_och_inte_pa_beloppet(client):
    """Ett fel nummer OCH en tom summa är två fel. Numret är det man skrev
    senast och det man vill höra om."""
    data = client.get("/swish-data?mottagare=12312345678").json()

    assert "tio siffror" in data["fel"]


def test_tom_fraga_ger_tomt_lage(client):
    data = client.get("/swish-data").json()

    assert data["lage"] == "tom"
    assert data["kodstrang"] is None


def test_last_tom_summa_ger_fel_ocksa_har(client):
    data = client.get("/swish-data?mottagare=1231234567").json()

    assert data["lage"] == "fel"
    assert "belopp" in data["fel"].lower()


def test_swish_data_ar_reserverad(client):
    """Adressen ligger före catch-all. En kortlänk med samma kod hade blivit
    oåtkomlig utan att någon förstod varför."""
    from app.config import RESERVED_CODES

    assert "swish-data" in RESERVED_CODES
