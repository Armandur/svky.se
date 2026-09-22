"""Nodträd och uppslag för gravplatslänkar (TASK-2145).

Adressen är `/10/had/hkn/allm/0446`: stift, enhet, kyrkogård, kvarter,
valfri avdelning, gravplatsnummer. Sökvägen ägs av gravplatsraden och fryses
när skylten trycks. Allt annat - koder, mallar, tema och kontaktuppgifter -
hämtas ur trädet vid uppslaget, så ett byte av verksamhetssystem blir tre
fält på en rad och en sammanslagning en flyttad pekare.

Leaf-modul: importerar bara från standardbiblioteket och app.config.
"""

import unicodedata
from urllib.parse import quote

# Nivåerna under stiftet, i ordning. Avdelningen är valfri och saknas i
# Härnösand. Namnen är leverantörernas egna, så ingen behöver översätta.
NIVAER = ("stift", "forvaltning", "kyrkogard", "kvarter", "avdelning")

# Så skriver Svenskagravar ihop beteckningen. Gravar.se har ett mellanslag
# mellan kyrkogård och kvarter, och sätter då en egen mall på sin nod.
PREFIXMALL_FORVAL = "{kgard}{quarter}"

# Fält som ärvs nedåt i trädet: första icke-tomma värdet på vägen upp.
ARVDA_FALT = (
    "prefixmall",
    "sokmall",
    "kartmall",
    "tema",
    "telefon",
    "epost",
    "url",
    "parish_id",
)

TEMAN = {"svky": "svky.se", "svk": "svenskakyrkan.se"}
TEMA_FORVAL = "svky"


# Ordet för nivån, till den som läser sidan. Ett kvarter som heter `Allm`
# säger ingenting ensamt - `Kvarter Allm` gör det.
NIVA_ORD = {
    "stift": "Stift",
    "forvaltning": "Förvaltning",
    "kyrkogard": "Kyrkogård",
    "kvarter": "Kvarter",
    "avdelning": "Avdelning",
}


def etikett(nod) -> str:
    """Vad noden heter på sidan.

    Kyrkogårdarna har riktiga namn: `HKN` är Härnösands nya kyrkogård. Ett
    kvarter har sällan något annat än sin kod, och då skriver vi koden
    ordagrant med nivåns ord framför: `Kvarter Allm`. Att hitta på
    `Kvarteret Allmänna` åt kvarteret `Allm` hade gett besökaren ett namn som
    inte står någonstans i systemet, och som personalen i telefonen inte
    känner igen.
    """
    if nod["namn"]:
        return nod["namn"]
    if nod["kod"]:
        ord_ = NIVA_ORD.get(nod["niva"])
        return f"{ord_} {nod['kod']}" if ord_ else nod["kod"]
    return nod["segment"]


class Gravplatsfel(Exception):
    """Fel som ska visas för den som redigerar, inte loggas och sväljas."""


def normalisera(varde: str) -> str:
    """NFC-normaliserar och gemenerar ett segment eller en sökväg.

    Samma synliga `sä` kan komma in som två eller tre kodpunkter beroende på
    tangentbord, filexport och webbläsare. Utan normalisering blir raden
    omöjlig att slå upp fast adressen ser rätt ut.

    Gemeneringen görs här och aldrig i SQL: SQLites LOWER() är ASCII-only och
    lämnar `SÄ` orört, så en jämförelse i databasen hade fungerat för alla
    kyrkogårdskoder utom just dem som bär åäö.
    """
    return unicodedata.normalize("NFC", varde).lower()


def dela_sokvag(sokvag: str) -> list[str]:
    """Delar en sökväg i normaliserade segment. Tomma segment faller bort."""
    return [normalisera(s) for s in sokvag.split("/") if s]


def sokvag_av(segment: list[str]) -> str:
    """Sätter ihop segment till en lagrad sökväg, utan inledande snedstreck."""
    return "/".join(normalisera(s) for s in segment)


# --------------------------------------------------------------------------
# Uppslag i trädet
# --------------------------------------------------------------------------


def hamta_gravplats(db, sokvag: str):
    """Gravplatsraden för en sökväg, frusen sökväg eller alias.

    Aliaset finns för att en sammanslagen organisation ska kunna trycka nya
    skyltar med sin nya kod medan de gamla skyltarna sitter kvar.
    """
    sokvag = normalisera(sokvag)
    rad = db.execute("SELECT * FROM gravplatser WHERE sokvag=?", (sokvag,)).fetchone()
    if rad:
        return rad
    return db.execute(
        """SELECT g.* FROM gravplatser g
           JOIN gravplats_alias a ON a.gravplats_id = g.id
           WHERE a.sokvag=?""",
        (sokvag,),
    ).fetchone()


def vandra(db, segment: list[str]) -> tuple[list, list[str]]:
    """Går ner i trädet så långt segmenten räcker.

    Returnerar kedjan av noder uppifrån och ner, plus de segment som inte
    matchade någon nod. Anroparen avgör vad resten betyder: inga kvar är en
    nodsida, ett kvar är en gravplats, fler än ett är ingenting alls.
    """
    kedja: list = []
    parent = 0
    for i, seg in enumerate(segment):
        rad = db.execute(
            "SELECT * FROM gravnoder WHERE parent_id=? AND segment=? AND pensionerad=0",
            (parent, seg),
        ).fetchone()
        if not rad:
            return kedja, segment[i:]
        kedja.append(rad)
        parent = rad["id"]
    return kedja, []


def kedja_till(db, nod_id: int) -> list:
    """Kedjan från roten ner till noden, uppifrån och ner."""
    kedja: list = []
    aktuell = nod_id
    while aktuell:
        rad = db.execute("SELECT * FROM gravnoder WHERE id=?", (aktuell,)).fetchone()
        if not rad:
            break
        kedja.insert(0, rad)
        aktuell = rad["parent_id"]
    return kedja


def barn(db, nod_id: int) -> list:
    """Nodens egna barn, i namnordning. Pensionerade noder utelämnas."""
    return db.execute(
        "SELECT * FROM gravnoder WHERE parent_id=? AND pensionerad=0 ORDER BY namn, segment",
        (nod_id,),
    ).fetchall()


# --------------------------------------------------------------------------
# Arv och mallar
# --------------------------------------------------------------------------


def arv(kedja: list, falt: str):
    """Närmaste satta värdet för ett fält, räknat nerifrån och upp.

    Ett tomt värde räknas som osatt. Förvaltningsnoden bär normalt mallarna,
    men en enskild kyrkogård får sätta ett eget värde som då gäller under den.
    """
    for nod in reversed(kedja):
        try:
            varde = nod[falt]
        except (IndexError, KeyError):
            continue
        if varde not in (None, ""):
            return varde
    return None


def arvda(kedja: list) -> dict:
    """Alla ärvda fält på en gång, som en vanlig dict för mallen."""
    return {falt: arv(kedja, falt) for falt in ARVDA_FALT}


def _kod(kedja: list, niva: str) -> str:
    for nod in kedja:
        if nod["niva"] == niva and nod["kod"]:
            return nod["kod"]
    return ""


def prefix(kedja: list) -> str:
    """Beteckningens prefix, byggt av nodernas koder enligt mallen.

    Regeln lästes ur Svenskagravars fältstruktur och höll på alla 14 423
    raderna i Härnösands export: kyrkogård och kvarter skrivs ihop, sedan
    avdelningen efter ett mellanslag när den finns.
    """
    mall = arv(kedja, "prefixmall") or PREFIXMALL_FORVAL
    ut = mall.replace("{kgard}", _kod(kedja, "kyrkogard")).replace(
        "{quarter}", _kod(kedja, "kvarter")
    )
    avdelning = _kod(kedja, "avdelning")
    if avdelning:
        ut = f"{ut} {avdelning}"
    return ut.strip()


def fullt_nummer(kedja: list, nummer: str) -> str:
    """Beteckningen som leverantören känner igen, t.ex. `HKNF 0446`."""
    pre = prefix(kedja)
    return f"{pre} {nummer}".strip() if pre else nummer


def _fyll(mall: str, full: str, plus_for_mellanslag: bool) -> str:
    kodat = quote(full, safe="")
    if plus_for_mellanslag:
        kodat = kodat.replace("%20", "+")
    return mall.replace("{full}", kodat)


def sok_url(kedja: list, nummer: str) -> str | None:
    """Söklänken hos leverantören. Ingen mall betyder ingen länk."""
    mall = arv(kedja, "sokmall")
    if not mall:
        return None
    return _fyll(mall, fullt_nummer(kedja, nummer), plus_for_mellanslag=True)


def kart_url(kedja: list, nummer: str) -> str | None:
    """Kartlänken. Valfri - Orust har ingen karta, och Gravar.se ingen alls."""
    mall = arv(kedja, "kartmall")
    if not mall:
        return None
    return _fyll(mall, fullt_nummer(kedja, nummer), plus_for_mellanslag=False)


def tema_av(kedja: list) -> str:
    valt = arv(kedja, "tema")
    return valt if valt in TEMAN else TEMA_FORVAL


# --------------------------------------------------------------------------
# Skrivning
# --------------------------------------------------------------------------


def satt_sokvag(db, gravplats_id: int, ny_sokvag: str) -> str:
    """Byter sökväg på en gravplats som ännu inte är tryckt.

    Två regler, och båda finns för att skylten sitter kvar i sten längre än
    organisationen står still:

    - Är gravplatsen markerad som tryckt är sökvägen låst. Att flytta den
      hade gjort en graverad QR-kod till en död adress.
    - Den gamla sökvägen blir ett alias och raderas aldrig. En frigjord
      adress går aldrig tillbaka i omlopp, samma regel som RESERVED_CODES
      och krockkontrollen i promoteringen.
    """
    rad = db.execute("SELECT * FROM gravplatser WHERE id=?", (gravplats_id,)).fetchone()
    if not rad:
        raise Gravplatsfel("Gravplatsen finns inte.")
    if rad["tryckt_at"]:
        raise Gravplatsfel("Sökvägen är låst - gravplatsen är markerad som tryckt.")

    ny = normalisera(ny_sokvag).strip("/")
    if not ny:
        raise Gravplatsfel("Sökvägen får inte vara tom.")
    if ny == rad["sokvag"]:
        return ny

    upptagen = db.execute(
        """SELECT 1 FROM gravplatser WHERE sokvag=? AND id<>?
           UNION ALL
           SELECT 1 FROM gravplats_alias WHERE sokvag=? AND gravplats_id<>?""",
        (ny, gravplats_id, ny, gravplats_id),
    ).fetchone()
    if upptagen:
        raise Gravplatsfel("Sökvägen är redan tagen av en annan gravplats.")

    # Gravplatsen slås upp före trädet, så en sökväg som pekar på en nod hade
    # skuggat nodens egen sida i stället för att krocka synligt.
    if vandra(db, dela_sokvag(ny))[1] == []:
        raise Gravplatsfel("Sökvägen pekar på en nod i trädet.")

    db.execute(
        "INSERT OR IGNORE INTO gravplats_alias (gravplats_id, sokvag) VALUES (?, ?)",
        (gravplats_id, rad["sokvag"]),
    )
    db.execute("UPDATE gravplatser SET sokvag=? WHERE id=?", (ny, gravplats_id))
    return ny
