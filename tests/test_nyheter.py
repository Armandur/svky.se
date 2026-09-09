"""Nyhetssidan: publik läsning, admin skriver.

Proven anropar ROUTEN och inte bara databasen. En sida som renderar rätt
säger ingenting om vem som släpps in, och det är behörighetsspärren som är
värd att mäta här.
"""

from app import database
from app.config import RESERVED_CODES


def test_publika_sidan_visar_innehallet(client):
    svar = client.get("/nyheter")

    assert svar.status_code == 200
    assert "Nyheter" in svar.text
    # Standardtexten seedas vid init. Utan den ser en tom sida likadan ut
    # som en trasig.
    assert "Så här funkar sidan" in svar.text


def test_footern_lankar_till_nyheter(client):
    """Sidan är oanvändbar om ingen hittar dit."""
    assert 'href="/nyheter"' in client.get("/").text


def test_koden_ar_reserverad():
    """/nyheter skuggar catch-all-routen GET /<kod>. Utan reservationen kan
    någon beställa kortkoden och få en länk som aldrig går att klicka på."""
    assert "nyheter" in RESERVED_CODES


def test_utloggad_nekas_redigeraren(client):
    svar = client.get("/admin/nyheter")

    assert svar.status_code == 303
    assert "/login" in svar.headers["location"]


def test_vanlig_anvandare_nekas_redigeraren(client, inloggad_anvandare):
    assert client.get("/admin/nyheter").status_code == 303


def test_admin_far_redigeraren(client, admin):
    svar = client.get("/admin/nyheter")

    assert svar.status_code == 200
    assert "/nyheter" in svar.text


def test_sparande_utan_csrf_nekas(client, admin):
    svar = client.post("/admin/nyheter", data={"content": "hej", "csrf_token": "fel"})

    assert svar.status_code == 403
    assert "hej" not in client.get("/nyheter").text


def test_admin_sparar_och_texten_syns_publikt(client, admin, hamta_csrf_token):
    token = hamta_csrf_token(client, "/admin/nyheter")

    svar = client.post(
        "/admin/nyheter",
        data={"content": "## Ny funktion\n\nQR-koder finns nu.", "csrf_token": token},
    )

    assert svar.status_code == 303
    publikt = client.get("/nyheter").text
    assert "Ny funktion" in publikt
    assert "QR-koder finns nu." in publikt


def test_om_redigeraren_sparar_markdown_i_databasen(client, admin, hamta_csrf_token):
    token = hamta_csrf_token(client, "/admin/om")
    markdown = "## Om tjänsten\n\nText med **fetstil** och [länk](/integritet)."

    svar = client.post(
        "/admin/om",
        data={"content": markdown, "csrf_token": token},
    )

    assert svar.status_code == 303
    with database.get_db() as db:
        sparat = db.execute("SELECT value FROM site_settings WHERE key='about_content'").fetchone()
    assert sparat is not None
    assert sparat["value"] == markdown


def test_admin_baren_lankar_till_nyheter(client, admin):
    assert 'href="/admin/nyheter"' in client.get("/admin/links").text


def test_senaste_nyheten_syns_pa_startsidan(client, admin, hamta_csrf_token):
    """Footern räckte inte. En nyhet ingen ser är samma sak som ingen nyhet."""
    token = hamta_csrf_token(client, "/admin/nyheter")
    client.post(
        "/admin/nyheter",
        data={
            "content": "## QR-koder\n\nVarje länk har nu en QR-kod.\n\n"
            "## Äldre post\n\nNågot som hände förut.",
            "csrf_token": token,
        },
    )

    text = client.get("/").text

    assert "Senaste nytt" in text
    assert "QR-koder" in text
    assert "Varje länk har nu en QR-kod." in text
    # Bara den senaste. Hela listan hör hemma på /nyheter.
    assert "Något som hände förut." not in text
    assert 'href="/nyheter"' in text


def test_nyheter_finns_i_navigeringen(client):
    """Länken ska följa med på varje sida, inte bara startsidan."""
    for sida in ("/", "/bestall", "/om"):
        svar = client.get(sida)
        assert svar.status_code == 200
        assert svar.text.count('href="/nyheter"') >= 2, f"{sida} saknar navlänken"


def test_text_utan_rubriker_visas_hel(client, admin, hamta_csrf_token):
    """Utan rubriker finns inga poster att välja mellan - då är texten ett
    stycke, och att klippa i den hade huggit av en mening."""
    token = hamta_csrf_token(client, "/admin/nyheter")
    client.post(
        "/admin/nyheter",
        data={"content": "Tjänsten är igång som vanligt.", "csrf_token": token},
    )

    assert "Tjänsten är igång som vanligt." in client.get("/").text


def test_tom_nyhetstext_ger_ingen_ruta(client, admin, hamta_csrf_token):
    token = hamta_csrf_token(client, "/admin/nyheter")
    client.post("/admin/nyheter", data={"content": "   ", "csrf_token": token})

    assert "Senaste nytt" not in client.get("/").text


def test_sidhuvudet_far_bryta_pa_smal_skarm():
    """Headern hade fast höjd och en enda rad, så navlänkarna sköt ut och
    sidan fick sidledes skroll (TASK-1695). Nyhetslänken gjorde det värre.

    Mätt i browser vid 320, 390, 600 och 1280px, in- och utloggad: ingen
    horisontell overflow. Provet låser reglerna som gör det möjligt.
    """
    css = (
        __import__("pathlib").Path(__file__).resolve().parents[1] / "app/static/style.css"
    ).read_text()
    mobil = css[css.index("Sidhuvudet på smal skärm") :]

    assert "flex-wrap: wrap" in mobil
    assert "height: auto" in mobil


def test_redigeraren_forklarar_klippregeln(client, admin):
    """Regeln syns inte i texten man skriver. Utan den här raden är det bara
    den som byggt sidan som vet varför halva nyheten hamnade på startsidan."""
    text = client.get("/admin/nyheter").text

    assert "Senaste nytt" in text
    assert "##" in text


def test_om_sidan_slipper_nyheternas_hjalptext(client, admin):
    """Om-sidan visas i sin helhet. En förklaring av en klippregel som inte
    gäller den hade bara varit brus."""
    text = client.get("/admin/om").text

    assert "Senaste nytt" not in text


def test_adminbaren_far_bryta_pa_smal_skarm():
    """Elva länkar i en rad som inte fick brytas gav 1104px innehåll i ett
    390px fönster - på VARJE admin-sida, inte bara den som råkade lägga
    till en länk.

    Mätt i browser vid 320, 390, 700 och 1280px på /admin/nyheter,
    /admin/links och /mina-lankar: ingen horisontell overflow.
    """
    css = (
        __import__("pathlib").Path(__file__).resolve().parents[1] / "app/static/style.css"
    ).read_text()
    mobil = css[css.index("Adminbaren på smal skärm") :]

    assert "flex-wrap: wrap" in mobil
