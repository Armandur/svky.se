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
