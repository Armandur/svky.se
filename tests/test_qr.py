"""QR-koder till kortlänkarna.

Proven avkodar bilderna. Att en route svarar 200 med image/png säger bara att
något kom ut - inte att det går att skanna, och inte att det bär rätt adress.
"""

import io

import cv2
import numpy as np
import pytest
import qrcode.constants
from PIL import Image

from app import qr
from app.database import get_db


def _avkoda(png: bytes) -> str:
    arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    text, *_ = cv2.QRCodeDetector().detectAndDecode(arr)
    return text


def _svg_till_png(svgdata: bytes) -> bytes:
    """Renderar UTAN att komponera mot vitt. En genomskinlig SVG blir då
    svart bakgrund och inverterad kod - vilket är precis felet vi vill
    fånga."""
    import cairosvg

    buf = io.BytesIO()
    cairosvg.svg2png(bytestring=svgdata, write_to=buf, output_width=900)
    im = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    ut = io.BytesIO()
    im.save(ut, format="PNG")
    return ut.getvalue()


def _skapa_lank(agare: int, code: str = "hsandkonf") -> int:
    with get_db() as db:
        db.execute(
            "INSERT INTO links (code, target_url, owner_id, status) VALUES (?,?,?,1)",
            (code, "https://www.svenskakyrkan.se/harnosand", agare),
        )
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


# --- modulen -------------------------------------------------------------

def test_koden_bar_kortlanken_inte_maladressen():
    """Byter länken mål ska en tryckt kod fortsätta fungera. Det är hela
    poängen med en kortlänk, och en kod på target_url hade förstört den."""
    adress = qr.lankadress("hsandkonf")
    assert adress.endswith("/hsandkonf")
    assert _avkoda(qr.png(adress)) == adress


def test_svg_har_vit_bakgrund():
    """SvgPathImage ritar bara banan, så filen blir genomskinlig. På färgat
    underlag inverteras koden och blir oläsbar. Provet renderar UTAN att
    komponera mot vitt - utan bakgrundsrektangeln avkodas den inte."""
    adress = qr.lankadress("hsandkonf")
    assert _avkoda(_svg_till_png(qr.svg(adress))) == adress


def test_marginalen_ar_minst_standardens_fyra():
    """En läsare behöver tyst yta för att hitta kanten. En tryckt kod utan
    den är oläsbar hur skarp den än är."""
    assert qr.MARGINAL_TRYCK >= 4


@pytest.mark.parametrize(
    ("code", "vantat"),
    [("hsandkonf", "svky-hsandkonf.svg"), ("../../etc/passwd", "svky-etcpasswd.svg"),
     ("!!!", "svky-kortlank.svg")],
)
def test_filnamnet_ar_ofarligt(code, vantat):
    assert qr.filnamn(code, "svg") == vantat


# --- routen --------------------------------------------------------------

@pytest.mark.parametrize("andelse", ["png", "svg"])
def test_agaren_far_hamta_sin_kod(client, inloggad_anvandare, andelse):
    lank = _skapa_lank(inloggad_anvandare["id"])

    svar = client.get(f"/mina-lankar/{lank}/qr.{andelse}")

    assert svar.status_code == 200
    assert svar.headers["content-type"].startswith(
        "image/png" if andelse == "png" else "image/svg+xml")
    assert "attachment" in svar.headers["content-disposition"]
    assert "svky-hsandkonf" in svar.headers["content-disposition"]

    png = svar.content if andelse == "png" else _svg_till_png(svar.content)
    assert _avkoda(png) == qr.lankadress("hsandkonf")


# Provet som bär behörigheten. Utan det räcker det att gissa ett id.
def test_annans_lank_ger_404(client, inloggad_anvandare):
    with get_db() as db:
        db.execute("INSERT INTO users (email) VALUES ('annan@svenskakyrkan.se')")
        annan = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    lank = _skapa_lank(annan, "annans")

    assert client.get(f"/mina-lankar/{lank}/qr.png").status_code == 404


def test_utloggad_skickas_till_login(client):
    assert client.get("/mina-lankar/1/qr.png").status_code == 303


def test_okand_andelse_ger_404(client, inloggad_anvandare):
    lank = _skapa_lank(inloggad_anvandare["id"])
    assert client.get(f"/mina-lankar/{lank}/qr.gif").status_code == 404


def test_admin_far_hamta_alla(client, admin):
    with get_db() as db:
        db.execute("INSERT INTO users (email) VALUES ('nagon@svenskakyrkan.se')")
        nagon = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    lank = _skapa_lank(nagon)

    svar = client.get(f"/admin/links/{lank}/qr.png")

    assert svar.status_code == 200
    assert _avkoda(svar.content) == qr.lankadress("hsandkonf")


def test_vanlig_anvandare_nekas_adminroutens_kod(client, inloggad_anvandare):
    lank = _skapa_lank(inloggad_anvandare["id"])
    assert client.get(f"/admin/links/{lank}/qr.png").status_code == 303


def _moduler(adress: str, felkorrigering: int) -> int:
    kod = qr._kod(adress, qr.MARGINAL_TRYCK, felkorrigering)
    return len(kod.get_matrix()) - 2 * qr.MARGINAL_TRYCK


def test_kortlank_ryms_i_25_moduler():
    """En autogenererad kod ska inte kosta ett versionssteg i onödan.

    Adressen skrivs ut med produktionens bas, inte lankadress() - provmiljön
    kör en längre BASE_URL, och det är den skarpa längden frågan gäller.
    H gav 29x29 moduler för samma adress. Skillnaden syns direkt på skärmen
    och i tryck: varje modul blir mindre, och koden ser tätare ut än den
    behöver vara när mitten ändå är tom.
    """
    adress = "https://svky.se/abcdefg"

    moduler = _moduler(adress, qr.FELKORRIGERING_LANK)

    assert moduler <= 25, f"{moduler}x{moduler} - kortlänken tog ett versionssteg extra"
    assert moduler < _moduler(adress, qr.FELKORRIGERING_SWISH)


def test_swish_behaller_hog_felkorrigering():
    """Symbolen i mitten täcker moduler. Utan H blir koden oläsbar."""
    assert qr.FELKORRIGERING_SWISH == qrcode.constants.ERROR_CORRECT_H
    assert qr.FELKORRIGERING_LANK != qr.FELKORRIGERING_SWISH


@pytest.mark.parametrize("symbol", sorted(qr.SYMBOLER))
def test_koden_avkodas_med_symbol(symbol):
    """Det enda utfall som betyder något: att koden går att läsa av.

    En sköld täcker moduler. Ritas matrisen med M och får symbolen pålagd
    efteråt ser bilden perfekt ut och skanningen faller - därför är det
    avkodningen som provas, inte att bilden blev till.
    """
    adress = qr.lankadress("hsandkonf")

    assert _avkoda(qr.png(adress, symbol=symbol)) == adress


@pytest.mark.parametrize("symbol", sorted(qr.SYMBOLER))
def test_svg_avkodas_med_symbol(symbol):
    """SVG-vägen räknar i moduler och PNG-vägen i pixlar. Två uträkningar av
    samma sak glider isär, så båda provas."""
    adress = qr.lankadress("hsandkonf")

    assert _avkoda(_svg_till_png(qr.svg(adress, symbol=symbol))) == adress


@pytest.mark.parametrize("symbol", sorted(qr.SYMBOLER))
def test_symbolen_hojer_felkorrigeringen(symbol):
    """Nivån måste väljas innan matrisen ritas, inte efter."""
    installning = qr.valj_symbol(symbol)

    assert qr._felkorrigering(installning) == qr.FELKORRIGERING_SWISH
    assert qr._felkorrigering(None) == qr.FELKORRIGERING_LANK


def test_okand_symbol_ger_ingen_symbol():
    """Värdet kommer ur en frågesträng. Ett okänt namn ska ge en kod utan
    sköld, inte ett fel - och aldrig fogas in i en sökväg."""
    assert qr.valj_symbol("../../etc/passwd") is None
    assert qr.valj_symbol("finns-inte") is None
    assert qr.valj_symbol(None) is None
    assert qr.valj_symbol("") is None


def test_symbolfilerna_finns():
    """Registret pekar på filer. Saknas en blir felet ett undantag mitt i en
    nedladdning, inte ett tomt svar."""
    for namn, installning in qr.SYMBOLER.items():
        assert installning.sokvag.exists(), f"{namn}: {installning.sokvag} saknas"


def test_symbolfilerna_bar_egen_ljus_yta():
    """Symbolen läggs rakt på koden, utan kontrastplatta under.

    Det håller bara så länge filen bär sin egen ljusa yta. En symbol som är
    mest genomskinlig får QR-mönstret rakt genom sig, och då behövs plattan
    tillbaka - se Symbolinstallning.
    """
    from PIL import Image

    for namn, installning in qr.SYMBOLER.items():
        alfa = Image.open(installning.sokvag).convert("RGBA").getchannel("A")
        genomskinliga = sum(1 for p in alfa.getdata() if p < 10)

        andel = genomskinliga / (alfa.size[0] * alfa.size[1])
        assert andel < 0.25, f"{namn}: {andel:.0%} genomskinligt, för lite egen yta"


def test_filnamnen_skiljer_symbolerna_at():
    """Ett paket med sex koder behöver sex olika namn. Två poster med samma
    namn i en zip behåller tyst bara den ena."""
    namn = {
        qr.filnamn("abc", andelse, symbol)
        for andelse in ("png", "svg")
        for symbol in (None, *qr.SYMBOLER)
    }

    assert len(namn) == 2 * (1 + len(qr.SYMBOLER))


@pytest.mark.parametrize("symbol", sorted(qr.SYMBOLER))
def test_routen_ger_koden_med_symbol(client, inloggad_anvandare, symbol):
    """Provet anropar ROUTEN. Att qr.png kan rita en sköld säger ingenting
    om att frågesträngen når fram."""
    lank = _skapa_lank(inloggad_anvandare["id"])

    svar = client.get(f"/mina-lankar/{lank}/qr.png?symbol={symbol}")

    assert svar.status_code == 200
    assert _avkoda(svar.content) == qr.lankadress("hsandkonf")
    assert symbol in svar.headers["content-disposition"]


def test_okand_symbol_ger_koden_utan_skold(client, inloggad_anvandare):
    """Värdet kommer utifrån. Ett okänt namn ska ge en kod, inte ett fel -
    och namnet får aldrig nå en sökväg."""
    lank = _skapa_lank(inloggad_anvandare["id"])

    svar = client.get(f"/mina-lankar/{lank}/qr.png?symbol=../../etc/passwd")

    assert svar.status_code == 200
    assert svar.content == qr.png(qr.lankadress("hsandkonf"))
    assert "passwd" not in svar.headers["content-disposition"]


def test_paketet_bar_alla_varianter(client, inloggad_anvandare):
    """Sex filer med sex OLIKA namn. Två poster med samma namn i en zip
    behåller tyst bara den ena."""
    import io
    import zipfile

    lank = _skapa_lank(inloggad_anvandare["id"])

    svar = client.get(f"/mina-lankar/{lank}/qr.zip")

    assert svar.status_code == 200
    assert svar.headers["content-type"] == "application/zip"
    namn = zipfile.ZipFile(io.BytesIO(svar.content)).namelist()
    assert len(namn) == len(set(namn)) == 2 * (1 + len(qr.SYMBOLER))
    for symbol in qr.SYMBOLER:
        assert any(symbol in n and n.endswith(".png") for n in namn)
        assert any(symbol in n and n.endswith(".svg") for n in namn)


def test_paketet_avkodas(client, inloggad_anvandare):
    """En zip som bär oläsbara koder är sämre än ingen zip."""
    import io
    import zipfile

    lank = _skapa_lank(inloggad_anvandare["id"])

    paket = zipfile.ZipFile(io.BytesIO(client.get(f"/mina-lankar/{lank}/qr.zip").content))

    for namn in paket.namelist():
        if namn.endswith(".png"):
            assert _avkoda(paket.read(namn)) == qr.lankadress("hsandkonf"), namn


def test_paketet_kraver_agarskap(client, inloggad_anvandare):
    """Samma spärr som de enskilda koderna. En zip vore annars vägen förbi."""
    with get_db() as db:
        db.execute("INSERT INTO users (email) VALUES ('nagon@svenskakyrkan.se')")
        nagon = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    lank = _skapa_lank(nagon)

    assert client.get(f"/mina-lankar/{lank}/qr.zip").status_code == 404


def test_paketet_kraver_inloggning(client):
    assert client.get("/mina-lankar/1/qr.zip").status_code == 303


def test_koden_far_en_etag(client, inloggad_anvandare):
    """En fast max-age räckte inte. Ritningen ändras - felkorrigeringen gick
    från H till M, och sköldarna kom dagen efter - och den som hämtat en kod
    satt då på den gamla bilden i upp till en timme utan att veta om det."""
    lank = _skapa_lank(inloggad_anvandare["id"])

    svar = client.get(f"/mina-lankar/{lank}/qr.png")

    assert svar.headers["etag"]
    # no-cache betyder "fråga först", inte "cacha inte".
    assert "no-cache" in svar.headers["cache-control"]
    assert "max-age" not in svar.headers["cache-control"]


def test_oforandrad_kod_ger_304(client, inloggad_anvandare):
    lank = _skapa_lank(inloggad_anvandare["id"])
    etag = client.get(f"/mina-lankar/{lank}/qr.png").headers["etag"]

    svar = client.get(f"/mina-lankar/{lank}/qr.png", headers={"If-None-Match": etag})

    assert svar.status_code == 304
    assert not svar.content


def test_gammal_etag_ger_ny_bild(client, inloggad_anvandare):
    """Det är det här fallet som gör ETaggen värd sitt anrop."""
    lank = _skapa_lank(inloggad_anvandare["id"])

    svar = client.get(f"/mina-lankar/{lank}/qr.png", headers={"If-None-Match": '"gammal"'})

    assert svar.status_code == 200
    assert _avkoda(svar.content) == qr.lankadress("hsandkonf")


def test_varje_variant_far_sin_egen_etag(client, inloggad_anvandare):
    """Delade två varianter etag skulle en växling ge fel bild ur cachen."""
    lank = _skapa_lank(inloggad_anvandare["id"])

    etaggar = {
        client.get(f"/mina-lankar/{lank}/qr.png?symbol={symbol}").headers["etag"]
        for symbol in ("", *qr.SYMBOLER)
    }

    assert len(etaggar) == 1 + len(qr.SYMBOLER)


def test_paketet_ar_deterministiskt(client, inloggad_anvandare):
    """Utan fast tidsstämpel skriver zipfile klockslaget i arkivet, och två
    paket med identiskt innehåll får olika etag - vilket gör den värdelös."""
    lank = _skapa_lank(inloggad_anvandare["id"])

    forst = client.get(f"/mina-lankar/{lank}/qr.zip")
    igen = client.get(f"/mina-lankar/{lank}/qr.zip")

    assert forst.content == igen.content
    assert forst.headers["etag"] == igen.headers["etag"]
    assert (
        client.get(
            f"/mina-lankar/{lank}/qr.zip", headers={"If-None-Match": forst.headers["etag"]}
        ).status_code
        == 304
    )


@pytest.mark.parametrize("symbol", sorted(qr.SYMBOLER))
def test_symbolen_ater_inte_upp_marginalen(symbol):
    """Skölden får inte bli så stor att koden bara nätt och jämnt går att
    läsa under perfekta förhållanden.

    Mätt 2026-09-08: marginalen mot smuts är oförändrad upp till 32 procent
    och kollapsar vid 35. Provet låser taket, inte det valda värdet - en
    höjning ska tvinga fram en ny mätning.
    """
    assert qr.SYMBOLER[symbol].andel <= 0.32


@pytest.mark.parametrize("symbol", sorted(qr.SYMBOLER))
def test_langa_koder_avkodas_med_symbol(symbol):
    """En egen kod kan vara mycket längre än en autogenererad, och en tätare
    matris beter sig inte som en gles."""
    adress = f"{qr.BASE_URL.rstrip('/')}/julkonsertharnosand2026"

    assert _avkoda(qr.png(adress, symbol=symbol)) == adress
