"""Gravplatslänkar: routing, arv, frysta sökvägar och låset (TASK-2145).

Proven anropar ROUTEN och inte modulen under den. En sökväg som löser rätt i
`app/gravplats.py` men aldrig kommer fram genom monteringsordningen är en
skylt i sten som pekar på en 404.
"""

import unicodedata

import pytest

from app.config import RESERVED_CODES, STIFT
from app.database import get_db
from app.validation import validate_code

HARNOSAND = {
    "sokmall": "https://svenskagravar.se/search?query={full}&parishId=28",
    "kartmall": "https://kartor-test.svenskagravar.se/webmap/#m=Harnosand,gravplatsnr={full}",
    "telefon": "0611-288 90",
    "epost": "harnosand.kyrkogard@svenskakyrkan.se",
}


def _nod(db, parent_id, niva, segment, namn, **falt):
    kolumner = ["parent_id", "niva", "segment", "namn", *falt.keys()]
    varden = [parent_id, niva, unicodedata.normalize("NFC", segment).lower(), namn, *falt.values()]
    db.execute(
        f"INSERT INTO gravnoder ({', '.join(kolumner)}) VALUES ({', '.join('?' * len(kolumner))})",
        varden,
    )
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def _gravplats(db, nod_id, sokvag, nummer, tryckt=False):
    db.execute(
        "INSERT INTO gravplatser (nod_id, sokvag, nummer, tryckt_at) VALUES (?, ?, ?, ?)",
        (
            nod_id,
            unicodedata.normalize("NFC", sokvag).lower(),
            nummer,
            "2026-09-22" if tryckt else None,
        ),
    )
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


@pytest.fixture
def harnosand(client):
    """Härnösands nya kyrkogård, kvarteret Allmänna, gravplats 0446.

    Samma rad som mätningarna i utredningen gjordes mot, så beteckningen i
    provet är den beteckning leverantören faktiskt svarar på.
    """
    with get_db() as db:
        stift = _nod(db, 0, "stift", "10", "Härnösands stift")
        forvaltning = _nod(
            db, stift, "forvaltning", "had", "Härnösands pastorat", tema="svky", **HARNOSAND
        )
        kyrkogard = _nod(db, forvaltning, "kyrkogard", "hkn", "Härnösands nya kyrkogård", kod="HKN")
        # Kvarteret heter `Allm` i Aveny-exporten och har inget annat namn.
        # Sidan skriver koden ordagrant, inte ett påhittat "Allmänna".
        kvarter = _nod(db, kyrkogard, "kvarter", "allm", None, kod="Allm")
        grav = _gravplats(db, kvarter, "10/had/hkn/allm/0446", "0446")
    return {
        "stift": stift,
        "forvaltning": forvaltning,
        "kyrkogard": kyrkogard,
        "kvarter": kvarter,
        "gravplats": grav,
    }


# --------------------------------------------------------------------------
# Landningssidan
# --------------------------------------------------------------------------


def test_gravplatssidan_visar_beteckning_och_lankar(client, harnosand):
    svar = client.get("/10/had/hkn/allm/0446")
    assert svar.status_code == 200
    assert "HKNAllm 0446" in svar.text
    assert "Härnösands nya kyrkogård" in svar.text
    assert "Kvarter Allm" in svar.text
    # Söklänken bär beteckningen kodad med plus för mellanslag, som
    # leverantörens egen sökruta skickar den.
    assert "svenskagravar.se/search?query=HKNAllm+0446" in svar.text
    assert "kartor-test.svenskagravar.se" in svar.text
    assert "0611-288 90" in svar.text


@pytest.mark.parametrize("tomt", [None, ""])
def test_kartkortet_goms_helt_utan_kartmall(client, harnosand, tomt):
    """Utan provet hade en tom mall gett en länk till `...gravplatsnr=` - en
    karta som laddar utan nål, vilket ser ut som ett fel i kartan.

    Båda tomma formerna prövas: NULL är raden som aldrig fått en mall, tom
    sträng är den som admin sparat ett blankt fält på.
    """
    with get_db() as db:
        db.execute("UPDATE gravnoder SET kartmall=? WHERE id=?", (tomt, harnosand["forvaltning"]))
    svar = client.get("/10/had/hkn/allm/0446")
    assert svar.status_code == 200
    assert "kartor-test" not in svar.text
    assert "kyrkogårdskartan" not in svar.text
    # Söklänken finns kvar - det är kartan som saknas, inte hela sidan.
    assert "svenskagravar.se/search" in svar.text


def test_oregistrerad_sokvag_ger_plats_och_kontakt_inte_naken_404(client, harnosand):
    svar = client.get("/10/had/hkn/allm/9999")
    assert svar.status_code == 200
    assert "Kvarter Allm" in svar.text
    assert "0611-288 90" in svar.text
    assert "inte registrerad" in svar.text
    # Ingen förifylld söklänk: segmentet är vår slug, inte gravplatsnumret.
    # `0009/17` slugas till `0009-17`, och en sökning på den formen ger noll
    # träffar hos leverantören - vilket läses som att graven inte finns.
    assert "svenskagravar.se/search" not in svar.text


def test_for_djup_sokvag_ger_404(client, harnosand):
    """Ett okänt segment under ett kvarter är en gravplats. Två är ingenting,
    och sidan får inte låtsas peka ut en plats den inte känner."""
    assert client.get("/10/had/hkn/allm/9999/8888").status_code == 404


def test_okand_segment_under_kyrkogard_ger_404(client, harnosand):
    """Kvarteret saknas, så sökvägen är inte välformad. Utan provet hade
    /10/had/hkn/struntprat renderat en gravplatssida utan kvarter."""
    assert client.get("/10/had/hkn/struntprat").status_code == 404


# --------------------------------------------------------------------------
# Nodsidorna
# --------------------------------------------------------------------------


def test_kyrkogarden_listar_sina_kvarter(client, harnosand):
    with get_db() as db:
        _nod(db, harnosand["kyrkogard"], "kvarter", "f", None, kod="F")
    svar = client.get("/10/had/hkn")
    assert svar.status_code == 200
    assert "Kvarter Allm" in svar.text
    assert "Kvarter F" in svar.text
    assert 'href="/10/had/hkn/allm"' in svar.text
    # Stiftet står i brödsmulan men får ingen länk: ett ensamt segment
    # fångas av catch-all för kortlänkar, så /10 är och förblir en 404.
    assert 'href="/10"' not in svar.text


def test_kvarteret_listar_inga_gravplatser(client, harnosand):
    """En lista över gravplatser hade gjort sidan till ett register över var
    människor ligger begravda. Numret får inte synas här."""
    svar = client.get("/10/had/hkn/allm")
    assert svar.status_code == 200
    assert "Kvarter Allm" in svar.text
    assert "0446" not in svar.text


# --------------------------------------------------------------------------
# Tecken, arv och tema
# --------------------------------------------------------------------------


def test_nfc_och_versaler_traffar_samma_rad(client, harnosand):
    """`sä` kan komma in som ett tecken eller som s + kombinerande prickar.

    Utan normaliseringen skulle den dekomponerade formen ge 404 medan den
    sammansatta ger 200 - samma synliga adress, olika svar. Provet skickar
    båda formerna plus versaler och kräver samma beteckning tillbaka.
    """
    with get_db() as db:
        kg = _nod(db, harnosand["forvaltning"], "kyrkogard", "sä", "Säbrå kyrkogård", kod="SÄ")
        kv = _nod(db, kg, "kvarter", "a", None, kod="A")
        _gravplats(db, kv, "10/had/sä/a/0001", "0001")

    sammansatt = client.get("/10/had/sä/a/0001")
    dekomponerad = client.get("/10/had/sä/a/0001")
    versaler = client.get("/10/had/SÄ/a/0001")

    assert sammansatt.status_code == 200
    assert dekomponerad.status_code == 200, "dekomponerat ä hittade inte raden"
    assert versaler.status_code == 200, "versalt Ä hittade inte raden"
    for svar in (sammansatt, dekomponerad, versaler):
        assert "SÄA 0001" in svar.text


def test_prefixmallen_arvs_och_gar_att_satta_per_forvaltning(client, harnosand):
    """Gravar.se skriver `Vä 16   516` med mellanslag. Byter en förvaltning
    verksamhetssystem ska det vara ett fält, inte en kodändring."""
    with get_db() as db:
        db.execute(
            "UPDATE gravnoder SET prefixmall=? WHERE id=?",
            ("{kgard} {quarter}", harnosand["forvaltning"]),
        )
    svar = client.get("/10/had/hkn/allm/0446")
    assert "HKN Allm 0446" in svar.text


def test_temat_arvs_till_bade_gravplats_och_nodsida(client, harnosand):
    with get_db() as db:
        db.execute("UPDATE gravnoder SET tema='svk' WHERE id=?", (harnosand["forvaltning"],))
    for vag in ("/10/had/hkn/allm/0446", "/10/had/hkn"):
        svar = client.get(vag)
        assert 'class="t-svk"' in svar.text, f"{vag} bär inte förvaltningens tema"


@pytest.mark.parametrize(
    "vag", ["/10/had/hkn/allm/0446", "/10/had/hkn/allm/9999", "/10/had/hkn", "/10/had/hkn/allm"]
)
def test_alla_gravsidor_ar_noindex(client, harnosand, vag):
    svar = client.get(vag)
    assert svar.status_code == 200
    assert 'name="robots" content="noindex' in svar.text
    assert "noindex" in svar.headers.get("X-Robots-Tag", "")


def test_typsnitten_laddas_bara_av_svenskakyrkan_temat(client, harnosand):
    """DM Sans och Spectral hör till svenskakyrkan.se-huden.

    Det som skulle ändras om felet fanns: svky-temat drar in 59 kB typsnitt
    det aldrig ritar med, på ett kyrkogårdsnät. Provet mäter länken i
    sidan, inte att filen finns.
    """
    with get_db() as db:
        db.execute("UPDATE gravnoder SET tema='svk' WHERE id=?", (harnosand["forvaltning"],))
    svk = client.get("/10/had/hkn/allm/0446").text
    assert "/static/fonts/dmsans-latin.woff2" in svk
    assert "/static/fonts/spectral-300-latin.woff2" in svk

    with get_db() as db:
        db.execute("UPDATE gravnoder SET tema='svky' WHERE id=?", (harnosand["forvaltning"],))
    svky = client.get("/10/had/hkn/allm/0446").text
    assert "woff2" not in svky


# --------------------------------------------------------------------------
# Frysta sökvägar, alias och låset
# --------------------------------------------------------------------------


def test_alias_loser_till_samma_gravplats(client, harnosand):
    with get_db() as db:
        db.execute(
            "INSERT INTO gravplats_alias (gravplats_id, sokvag) VALUES (?, ?)",
            (harnosand["gravplats"], "10/nyaenheten/hkn/allm/0446"),
        )
    via_alias = client.get("/10/nyaenheten/hkn/allm/0446")
    assert via_alias.status_code == 200
    assert "HKNAllm 0446" in via_alias.text


def test_sokvagen_gar_att_andra_innan_den_ar_tryckt(client, admin, harnosand, hamta_csrf_token):
    token = hamta_csrf_token(client, "/admin/gravplatser")
    svar = client.post(
        f"/admin/gravplatser/{harnosand['gravplats']}/sokvag",
        data={"sokvag": "10/had/hkn/allm/0446b", "csrf_token": token},
    )
    assert svar.status_code == 303
    assert client.get("/10/had/hkn/allm/0446b").status_code == 200
    # Gamla sökvägen lever kvar som alias och går aldrig till någon annan.
    assert client.get("/10/had/hkn/allm/0446").status_code == 200


def test_tryckt_sokvag_ar_last(client, admin, harnosand, hamta_csrf_token):
    """Låset mäts på sökvägen i databasen, inte på felmeddelandet. Faller
    spärren står adressen kvar som `...0446b` medan en graverad QR-kod pekar
    på `...0446`."""
    with get_db() as db:
        db.execute(
            "UPDATE gravplatser SET tryckt_at=CURRENT_TIMESTAMP WHERE id=?",
            (harnosand["gravplats"],),
        )
    # Tokenet hämtas från en annan adminvy: listan visar inget formulär för
    # en tryckt gravplats, och provet ska mäta spärren i routen - inte att
    # mallen råkar dölja fältet.
    token = hamta_csrf_token(client, "/admin/domaner")
    client.post(
        f"/admin/gravplatser/{harnosand['gravplats']}/sokvag",
        data={"sokvag": "10/had/hkn/allm/0446b", "csrf_token": token},
    )
    with get_db() as db:
        kvar = db.execute(
            "SELECT sokvag FROM gravplatser WHERE id=?", (harnosand["gravplats"],)
        ).fetchone()["sokvag"]
    assert kvar == "10/had/hkn/allm/0446"


def test_sokvag_som_pekar_pa_en_nod_avvisas(client, admin, harnosand, hamta_csrf_token):
    """Gravplatsen slås upp före trädet. Utan spärren hade en gravplats på
    `10/had/hkn/allm` skuggat kvarterets egen sida."""
    token = hamta_csrf_token(client, "/admin/gravplatser")
    client.post(
        f"/admin/gravplatser/{harnosand['gravplats']}/sokvag",
        data={"sokvag": "10/had/hkn/allm", "csrf_token": token},
    )
    with get_db() as db:
        kvar = db.execute(
            "SELECT sokvag FROM gravplatser WHERE id=?", (harnosand["gravplats"],)
        ).fetchone()["sokvag"]
    assert kvar == "10/had/hkn/allm/0446"
    assert "Kvarter Allm" in client.get("/10/had/hkn/allm").text


def test_visningar_raknas_utan_persondata(client, harnosand):
    client.get("/10/had/hkn/allm/0446")
    client.get("/10/had/hkn/allm/0446")
    with get_db() as db:
        antal = db.execute("SELECT COUNT(*) FROM gravplats_views").fetchone()[0]
        kolumner = {r[1] for r in db.execute("PRAGMA table_info(gravplats_views)")}
    assert antal == 2
    # Samma linje som clicks och bundle_views: bara tidsstämpel och id.
    assert kolumner == {"id", "gravplats_id", "viewed_at"}


# --------------------------------------------------------------------------
# Grannarna
# --------------------------------------------------------------------------


def test_catch_all_svarar_fortfarande_pa_en_vanlig_kortkod(client, harnosand):
    """Gravroutern monteras före catch-all. Faller den här hade varenda
    kortlänk slutat fungera, vilket är ett större fel än att gravsidan saknas."""
    with get_db() as db:
        db.execute(
            "INSERT INTO links (code, target_url, status) VALUES (?, ?, 1)",
            ("hsandkonf", "https://www.svenskakyrkan.se/harnosand"),
        )
    svar = client.get("/hsandkonf")
    assert svar.status_code == 302
    assert svar.headers["location"] == "https://www.svenskakyrkan.se/harnosand"


@pytest.mark.parametrize("kod", sorted(STIFT))
def test_stiftskoderna_gar_inte_att_bestalla_som_kortlank(kod):
    assert kod in RESERVED_CODES
    assert validate_code(kod) is not None, f"{kod} gick att beställa som kortkod"
