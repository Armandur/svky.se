"""Vad en betalning tillåter, sagt på svenska.

Egen modul för att både generatorn och samlingen visar samma sak, och för
att app/swish.py ska få vara ren format- och beteendekunskap utan
gränssnittstexter i sig.
"""

from __future__ import annotations

from app.swish import Swishbetalning, fria_falt

# Fältnamnen som de heter för den som fyller i, inte som de heter i koden.
_FALTNAMN = {
    "belopp": "beloppet",
    "meddelande": "meddelandet",
    "mottagare": "mottagarnumret",
}


def _rada_upp(delar: list[str]) -> str:
    """a, b och c - inte a, b, c. Meningen ska gå att läsa högt."""
    if len(delar) == 1:
        return delar[0]
    return ", ".join(delar[:-1]) + " och " + delar[-1]


def lastext(betalning: Swishbetalning) -> str:
    """Vad betalaren kan ändra, i klartext och för de ifyllda värdena.

    Ersätter den statiska raden "Det som inte är ikryssat låses i appen".
    Den stämde inte: mottagaren följer med så fort något annat fält är
    fritt, oavsett vad kryssrutan säger. En rad som räknar upp kryssrutorna
    hade alltså sagt emot verkligheten på just den punkt som betyder mest.
    """
    # Visa värdena som de kommer att stå i koden, inte som de skrevs in.
    ren = betalning.normaliserad()
    fria = fria_falt(betalning)

    if not fria:
        return f"Allt är låst. Betalaren kan bara godkänna {ren.belopp} kr till {ren.mottagare}."

    text = "Betalaren kan ändra " + _rada_upp([_FALTNAMN[f] for f in fria]) + "."
    if not betalning.redigerbar_mottagare:
        # Utan den här meningen ser mottagaren ut att vara fri av misstag.
        text += (
            " Mottagarnumret följer med så fort något annat fält är fritt, även utan kryssrutan."
        )

    # Ett tomt meddelande finns inte att låsa, och beloppet är alltid fritt
    # när det saknas - annars hade betalningen inte gått att koda alls.
    lasta = [
        namn
        for nyckel, namn in _FALTNAMN.items()
        if nyckel not in fria and (nyckel != "meddelande" or ren.meddelande)
    ]
    if lasta:
        text += " Låst: " + _rada_upp(lasta) + "."
    return text
