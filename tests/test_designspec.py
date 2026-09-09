"""Håller docs/design.md:s räknebara påståenden sanna.

Specen visade sig bära flera påståenden om verifiering som aldrig kördes -
"kontrollerat att X aldrig händer" där X hände. Proven här mäter de
påståenden som GÅR att mäta, så nästa avvikelse syns när den uppstår i
stället för nästa gång någon läser dokumentet.

Detta är inte en fullständig granskning av specen. Regler om ton, rubriker
och när ett kort är rätt komponent går inte att prova så här - de vilar
fortfarande på läsning.
"""

import re
from pathlib import Path

ROT = Path(__file__).resolve().parents[1]
MALLAR = ROT / "app" / "templates"
SPEC = ROT / "docs" / "design.md"


def _mallar():
    return sorted(MALLAR.rglob("*.html"))


def test_farliga_och_primara_knappar_ar_rena_ord():
    """§1 och §6: en primär eller farlig knapp bär inga ikoner.

    Den ska vara entydig utan att en font behöver rendera rätt glyf, och
    inget ska dra blicken åt en annan riktning från det som tar bort något.
    Emoji-som-prefix hör till sekundärknappar.
    """
    med_ikon = []
    for f in _mallar():
        text = f.read_text(encoding="utf-8")
        for klass in ("btn-primary", "btn-danger"):
            for m in re.finditer(rf'class="btn {klass}[^"]*"(.*?)</(?:button|a)>', text, re.S):
                inre = m.group(1)
                synligt = inre.split(">", 1)[1] if ">" in inre else inre
                if re.search(r"&#\d+;|&#x[0-9a-fA-F]+;|[\U0001F300-\U0001FAFF]", synligt):
                    med_ikon.append(f"{f.relative_to(MALLAR)} ({klass}): {synligt.strip()[:40]}")

    assert med_ikon == [], med_ikon


def test_specen_raknar_upp_alla_mallar_med_panel():
    """§8: sidan påstod att panelen fanns i två mallar när den fanns i en.

    Provet håller uppräkningen ärlig åt båda håll: sprids panelen till fler
    mallar är det goda nyheter, men specen ska uppdateras samtidigt i
    stället för att tystna om att de gått isär.
    """
    spec = SPEC.read_text(encoding="utf-8")
    med_panel = sorted(
        f.name for f in _mallar() if "confirm-overlay" in f.read_text(encoding="utf-8")
    )

    assert med_panel == ["mina_swishsamlingar_detalj.html", "my_links.html"], med_panel
    for mall in med_panel:
        assert mall.removesuffix(".html") in spec, f"{mall} nämns inte i avsnitt 8"


def test_confirm_ligger_inte_i_fler_mallar_an_specen_sager():
    """§8: 22 förekomster i 9 mallar. Regeln säger att confirm() ska fasas
    ut, så antalet får sjunka men inte stiga - en ny destruktiv knapp ska
    följa panelen, inte webbläsardialogen.
    """
    mallar = [f for f in _mallar() if "return confirm(" in f.read_text(encoding="utf-8")]
    forekomster = sum(f.read_text(encoding="utf-8").count("return confirm(") for f in mallar)

    # Taket sänks varje gång en mall konverteras, aldrig höjs. Just nu:
    # 21 förekomster i 8 mallar.
    assert len(mallar) <= 8, [f.name for f in mallar]
    assert forekomster <= 21, forekomster


def test_inget_falt_har_placeholder_som_enda_etikett():
    """§4: aldrig placeholder som enda etikett.

    En placeholder försvinner så fort någon börjar skriva, och den som
    lyssnar hör den inte alls. Sökrutor får bära sin etikett som
    `aria-label` - där är en ensam placeholder etablerad konvention och en
    synlig etikett hade sagt "Sök" bredvid en knapp som säger "Sök" - men
    märkta ska de vara.

    Provet faller om ett fält varken har <label for=...>, en <label> i sin
    form-group, eller en aria-label.
    """
    omarkta = []
    for f in _mallar():
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r'<input[^>]*placeholder="[^"]+"[^>]*>', text):
            tagg = m.group(0)
            if 'type="hidden"' in tagg:
                continue
            if "aria-label=" in tagg:
                continue
            ident = re.search(r'id="([^"]+)"', tagg)
            if ident and f'for="{ident.group(1)}"' in text:
                continue
            if "<label" in text[max(0, m.start() - 300) : m.start()]:
                continue
            namn = re.search(r'name="([^"]+)"', tagg)
            omarkta.append(f"{f.name}:{namn.group(1) if namn else '?'}")

    assert omarkta == [], omarkta


def test_specens_radhanvisningar_pekar_pa_det_de_pastar():
    """En radhänvisning som glidit är värre än ingen: den ser kontrollerad
    ut. Prövar de som specen citerar med innehåll."""
    fall = [
        ("app/static/style.css", 46, "main.wide"),
        ("app/static/style.css", 140, ".form-group"),
        ("app/templates/_ansok_upplysning.html", 4, "Ansök om rätt att länka"),
        ("app/templates/admin/users.html", 285, "btn-danger"),
    ]
    for fil, rad, vantat in fall:
        rader = (ROT / fil).read_text(encoding="utf-8").splitlines()
        assert vantat in rader[rad - 1], f"{fil}:{rad} bär inte {vantat!r}"
