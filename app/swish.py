"""Swish-betallänkar: QR-strängen och applänken.

Modulen bygger BARA de två strängarna. Ritningen ligger i app/qr.py, och
inget här rör Swish Handel-API, certifikat eller betalningsuppföljning - vi
skickar aldrig något till mpc.getswish.net.

Formaten kommer från Swish "Guide Swish QR code design specification" v1.7.2
avsnitt 6.1, och från den implementation som är i drift i slöjda.de. Se
docs/swish-qr.md, som är den kanoniska specen och rättar två fel i det
ursprungliga underlaget.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote

# Vad betalaren får ändra i appen efter skanning. Bit satt betyder REDIGERBAR,
# alltså tvärtom mot vad namnet "lock" antyder. Utelämnad mask tolkas som 0,
# vilket låser allt.
#
# Masken låser INTE mottagaren när något annat fält är fritt. Mätt på telefon
# 2026-09-08: en skannad kod med mask 2 låter betalaren byta nummer, precis
# som applänken. Bara mask 0 håller numret.
REDIGERBAR_MOTTAGARE = 1
REDIGERBART_BELOPP = 2
REDIGERBART_MEDDELANDE = 4

# Swish-appen visar och sparar bara 50 tecken, medan schemat för QR-API:t
# anger 70. Den snävare gränsen är den som gäller för det användaren ser.
MAX_MEDDELANDE = 50


class Swishfel(ValueError):
    """Indata som inte går att koda."""


@dataclass(frozen=True)
class Swishbetalning:
    """En betalning som ska bli en kod och en länk.

    `belopp` är kronor som sträng eller None. None betyder att betalaren
    fyller i själv, och då MÅSTE beloppet vara redigerbart - en låst tom
    summa går inte att betala.
    """

    mottagare: str
    belopp: str | None = None
    meddelande: str | None = None
    redigerbar_mottagare: bool = False
    redigerbart_belopp: bool = False
    redigerbart_meddelande: bool = False

    def normaliserad(self) -> Swishbetalning:
        """Samma betalning med fälten på sin lagringsform.

        "070-123 45 67" och "0701234567" är samma nummer, "100" och "100,00"
        samma belopp - men bara den ena formen går att jämföra mot en tryckt
        lapp. Anropas före den sparas, aldrig i kodningen: qr_strang() och
        applank() normaliserar redan var för sig.
        """
        return Swishbetalning(
            mottagare=_rensa_mottagare(self.mottagare),
            belopp=_kronor(self.belopp) or None,
            meddelande=_meddelande(self.meddelande) or None,
            redigerbar_mottagare=self.redigerbar_mottagare,
            redigerbart_belopp=self.redigerbart_belopp,
            redigerbart_meddelande=self.redigerbart_meddelande,
        )

    def mask(self) -> int:
        return (
            (REDIGERBAR_MOTTAGARE if self.redigerbar_mottagare else 0)
            + (REDIGERBART_BELOPP if self.redigerbart_belopp else 0)
            + (REDIGERBART_MEDDELANDE if self.redigerbart_meddelande else 0)
        )


def _rensa_mottagare(varde: str) -> str:
    siffror = "".join(t for t in (varde or "") if t.isdigit())
    if len(siffror) != 10:
        raise Swishfel("Swish-numret ska vara tio siffror.")
    return siffror


def _kronor(belopp: str | None) -> str:
    """Beloppet på QR-strängens form: två decimaler och decimalkomma.

    Swish vill ha 100,00 och inte 100. Applänken vill däremot ha hela kronor
    utan komma, så de två formaten får inte blandas ihop - se applank().

    Ören går bra, både 149,50 och 149.50. Fler än två decimaler AVVISAS i
    stället för att avrundas: den som skriver 10,999 får annars en tryckt
    kod på 11 kronor utan att veta om det.
    """
    if belopp in (None, ""):
        return ""
    text = str(belopp).strip().replace(",", ".")
    heltal, punkt, decimaler = text.partition(".")
    if punkt and len(decimaler) > 2:
        raise Swishfel("Beloppet kan ha högst två decimaler, alltså ören.")
    try:
        tal = float(text)
    except ValueError:
        raise Swishfel("Beloppet går inte att tolka som ett tal.") from None
    if tal <= 0:
        raise Swishfel("Beloppet måste vara större än noll.")
    if tal >= 1_000_000:
        raise Swishfel("Beloppet är för stort.")
    return f"{tal:.2f}".replace(".", ",")


def _meddelande(text: str | None) -> str:
    return (text or "").strip()[:MAX_MEDDELANDE]


def _kontrollera(betalning: Swishbetalning) -> None:
    """Det som gör en kod obetalbar, fångat före den ritas.

    En tryckt kod går inte att rätta i efterhand, så felen ska mötas i
    beställningen och inte på anslagstavlan.

    Mottagaren prövas FÖRST. Är numret fel är det numret man vill höra om,
    inte beloppet - ett elvasiffrigt nummer och en tom summa gav förut ett
    felmeddelande om beloppet, och den som läste det letade på fel rad.
    """
    _rensa_mottagare(betalning.mottagare)
    if not betalning.belopp and not betalning.redigerbart_belopp:
        raise Swishfel("En kod utan förifyllt belopp måste låta betalaren fylla i det själv.")


def qr_strang(betalning: Swishbetalning) -> str:
    """Innehållet i QR-koden.

    Formen är C<mottagare>;<belopp>;<meddelande>;<mask>. Tomma fält behålls
    som tom sträng mellan semikolonen, alltså C1231234567;;;6 för en gåva.
    """
    _kontrollera(betalning)
    mottagare = _rensa_mottagare(betalning.mottagare)
    belopp = _kronor(betalning.belopp)
    # URL-kodat enligt specen. quote lämnar bokstäver och siffror i fred och
    # kodar mellanslag som %20, inte som plus.
    meddelande = quote(_meddelande(betalning.meddelande), safe="")
    return f"C{mottagare};{belopp};{meddelande};{betalning.mask()}"


def applank(betalning: Swishbetalning) -> str:
    """swish://payment?data=<URL-kodad JSON>.

    Formatet är inte dokumenterat av Swish utan härlett ur appen, därav den
    egna funktionen: byts det ut rör ändringen bara den här koden.

    VARNING: så fort något fält bär editable går MOTTAGAREN att ändra i
    appen, oavsett vad payee säger. Mätt 2026-09-08, och editable: false på
    payee hjälper inte. En applänk med fria fält låter alltså den som
    klickar peka om betalningen till ett annat nummer.

    Detsamma gäller den SKANNADE koden. Rättat 2026-09-08 efter mätning på
    telefon: låsmasken i qr_strang styr vilka fält appen öppnar för
    redigering, men den fäster inte mottagaren. Bara en betalning där alla
    fält är låsta håller numret. Docstringen påstod tidigare att QR-koden
    var det säkra valet för tryck - det stämde inte.

    En gåva med fritt belopp uttrycks genom att amount-nyckeln UTELÄMNAS
    helt. Appen öppnas då med ett tomt beloppsfält och meddelandet kvar.
    Uppmätt på telefon 2026-09-08: tom sträng, noll och null fungerar alla
    sämre eller inte alls, och strängen "0" tvingar givaren att ändra från
    noll med en varning om att en krona är minsta belopp.
    """
    _kontrollera(betalning)
    # version är TALET 1, inte strängen "1.0". Uppmätt på telefon
    # 2026-09-08: en länk med strängen öppnar Swish men fyller inte i
    # någonting, och det är den enda skillnaden mellan en länk som
    # fungerar och en som inte gör det. docs/swish-qr.md påstod motsatsen
    # och är rättad.
    data: dict[str, object] = {
        "version": 1,
        "payee": {"value": _rensa_mottagare(betalning.mottagare)},
    }
    if betalning.redigerbar_mottagare:
        data["payee"]["editable"] = True  # type: ignore[index]

    belopp = _kronor(betalning.belopp)
    if belopp:
        # Ett TAL, och hela beloppet inklusive ören. Tidigare skickades
        # bara heltalsdelen som sträng, så 149,50 blev 149 och femtio öre
        # försvann tyst.
        tal = float(belopp.replace(",", "."))
        data["amount"] = {"value": int(tal) if tal == int(tal) else tal}
        if betalning.redigerbart_belopp:
            data["amount"]["editable"] = True  # type: ignore[index]
    # Utan belopp utelämnas nyckeln helt. Se docstringen.

    text = _meddelande(betalning.meddelande)
    if text:
        data["message"] = {"value": text}
        if betalning.redigerbart_meddelande:
            data["message"]["editable"] = True  # type: ignore[index]

    # separators utan mellanslag: länken hamnar i en href och i en QR-kod,
    # och varje tecken kostar där.
    nyttolast = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"swish://payment?data={quote(nyttolast, safe='')}"


def betalning_ur_rad(rad) -> Swishbetalning:
    """En sparad swishpost som betalning.

    Raden kommer ur swish_items och bär samma fält som formuläret, men med
    heltal 0/1 där dataklassen vill ha bool.
    """
    return Swishbetalning(
        mottagare=rad["mottagare"],
        belopp=rad["belopp"] or None,
        meddelande=rad["meddelande"] or None,
        redigerbar_mottagare=bool(rad["fri_mottagare"]),
        redigerbart_belopp=bool(rad["fritt_belopp"]),
        redigerbart_meddelande=bool(rad["fritt_meddelande"]),
    )
