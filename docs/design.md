# Designspec för svky.se

Uppslagsverk, inte kurslitteratur. Reglerna här är grundade i hur
`app/static/style.css` (405 rader) och mallarna i `app/templates/` faktiskt
ser ut idag, med filnamn och radnummer. Där en regel ändrar nuläget står det
uttryckligen, med motivering.

Färgvariablerna i `style.css:5-24` (`--blue`, `--green`, `--red`, `--orange`
osv) ligger fast. Den här specen bygger komponenter av dem, den byter
inte ut dem.

## 1. Knappar: primär, sekundär, farlig, textlänk

Fyra klasser finns: `.btn-primary` (63 träffar), `.btn-secondary` (99),
`.btn-danger` (24), och vanlig `<a>` utan btn-klass. `.btn-sm` (141 träffar)
lägger på mindre padding ovanpå någon av de tre.

**Regeln, härledd ur hur koden faktiskt använder dem:**

- **Primär** = den handling sidan finns till för, en gång per formulär/vy.
  `bestall.html:` "Skicka beställning", `admin/create_link.html`: "Skapa
  länk", `my_links.html:267`: "Spara ändring" i det öppnade
  redigeringsformuläret. Finns bara en primärknapp synlig åt gången i ett
  givet formulär - annars vet ögat inte var det ska landa.
- **Sekundär** = alla övriga handlingar som inte är destruktiva: navigera,
  öppna ett formulär, ladda ner, avbryta. Detta är default-knappen. Att den
  står för 99+141 träffar är rätt, inte ett tecken på slarv - de flesta
  handlingar på en lista med tio kort *är* sekundära i förhållande till
  kortets egen huvuduppgift.
- **Farlig** (`.btn-danger`, bakgrund `--red-bg`, text `--red`,
  `style.css:190`) = handlingen tar bort, avaktiverar eller raderar något.
  Används konsekvent: `Avaktivera`, `Radera mitt konto`, `Radera {{ e-post
  }}`, `Ta bort`. Kontrollerat: `.btn-danger` har **aldrig** en emoji-ikon
  (se avsnitt 6) - farliga knappar ska vara rena ord, inget som drar blicken
  åt en annan riktning.
- **Textlänk** (ingen btn-klass) = navigation som inte är sidans
  primäruppgift och inte radbrytande viktig: `Logga in` i sidfoten av ett
  formulär, `Mina länkar` i brödsmulor, länkar i löptext.

**Rasmus fråga: ska "Ansök om rätt att länka externt" vara en knapp eller en
textlänk?**

Idag är den en ren `<a>` inne i en `.alert-info`
(`_ansok_upplysning.html:4`). Regeln: **en åtgärdslänk som ligger inuti en
`.alert` ärver alertens vikt, inte knapparnas.** En alert är redan en visuellt
avgränsad ruta - att lägga en knapp i en ruta som redan har egen bakgrund och
kant dubblerar signalen och ser aldrig bra ut (jämför med hur `admin/
domains.html` och `bestall.html` bara sätter länkar rakt i sin `alert-warning`/
`alert-error`-text). Håll den som textlänk. Ändra INTE.

Omvänt: en handling som INTE bor i en informationsruta, utan står fritt i ett
kort eller under en tabell, ska vara en knapp - annars försvinner den. Det är
skillnaden mellan `_ansok_upplysning.html:4` (textlänk, rätt) och till exempel
`my_links.html:230` "Ändra mål-URL" (knapp, rätt, står fritt i `.link-actions`).

**Kort regel att slå upp:** *Ligger handlingen i en `.alert` → textlänk. Står
den fritt i ett kort, en rad i en tabell eller ett `.link-actions`-stråk →
knapp, sekundär som default, farlig om den tar bort/avaktiverar/raderar,
primär bara en gång per formulär.*

## 2. Alert vs löptext

Fyra varianter i `style.css:196-208`: `alert-success` (grön), `alert-warning`
(orange), `alert-error` (röd), `alert-info` (blå). Alla har `display:flex`
och är tänkta att ta en emoji/ikon plus text (se `_ansok_upplysning.html`,
`bestall.html:` felmeddelanden).

**En alert är statusen på en handling som sidan just utfört eller är på väg
att utföra** - "Länken skapad", "Domänen är redan tillagd", "Det här kräver
bekräftelse". Den ligger *ovanför* huvudinnehållet eller precis vid det
formulär den hör till, aldrig nedsänkt i löptext.

**Löptext** är allt som beskriver hur tjänsten fungerar utan att vara en
reaktion på något användaren gjorde: hjälptexter under fält
(`.form-group .hint`, `style.css:147`), beskrivningar av vad en knapp gör
(`bestall.html`: "Kräver e-postverifiering." under Kortlänk-kortet).

Regel: **fråga "är det här ett svar på en handling, eller bakgrundsfakta?"**
Svar → alert. Fakta → löptext eller `.hint`. Exempel på att det redan följs
rätt: `admin/om_edit.html:50` lägger sin permanenta hjälptext i en `alert-info
hjalpruta` - det är en gränsdragning man kan diskutera (den är fakta, inte ett
svar), men eftersom `hjalpruta` sätter egen padding/font-storlek är den de
facto en egen komponent som råkar återanvända alert-färgen. Se fynd-listan.

## 3. Kort: vad är det, när används det

`.card` (`style.css:127-133`): vit bakgrund, kant, skugga, rundade hörn,
28×32px padding. Två användningssätt existerar sida vid sida:

1. **Sidkort** - en ensam `.card` som omsluter HELA huvudinnehållet på en
   smal formulärsida: `login.html`, `bestall.html`, `404.html`, `error.html`.
   Ett enda kort, centrerat, `max-width` satt av `main` (900px) eller en egen
   `center-card`-klass (`error.html`).
2. **Listkort** - varje rad i en lista är ett eget kort:
   `.link-card` (`my_links.html:6-9`), `.stat-card` (`style.css:274-284`),
   `.link-card` i sig upprepar exakt `.card`s deklaration (bakgrund, kant,
   radius, padding, skugga) med egna klassnamn istället för att komponera
   `.card` - se fynd-listan.

**Regel:** ett kort är enheten för "en sak jag kan agera på för sig". En
lista med tio länkar → tio kort, inte en tabell, eftersom varje länk har fem
knappar och två dolda paneler (redigera, QR, bekräfta) som bara får plats i
ett kort. En tabell (`admin/links.html`, `admin/users.html` för siffrorna)
används när raden är läsdata utan egna dolda paneler och radhöjden ska hållas
nere.

Meningen "`admin/links.html` har fortfarande knappar per rad, men bara tre
smala, så tabellen bär dem" stod här och var fel: de tre knapparna sitter i
en cell med `white-space: nowrap` och driver 59 px överflöd även på en bred
skärm. Att en tabell "bär" sina knappar är inte något man antar, det är
något avsnitt 10 räknar.

Ny regel (litet tillägg, inte i kod idag): **återanvänd `.card` för nya
listkort i stället för att skriva en ny klass med samma fem deklarationer.**
Skriv bara det som skiljer (t.ex. `.link-card.inactive { opacity: .75; }`)
som ett tillägg ovanpå `.card`.

## 4. Formulär: etikett, hjälptext, fel

Mönstret sitter i `style.css:140-168` och upprepas konsekvent:

```html
<div class="form-group">
  <label>Fältnamn</label>
  <input type="text" ...>
  <div class="hint">Hjälptext under fältet.</div>
  {% if fel %}<div class="field-error">{{ fel }}</div>{% endif %}
</div>
```

- **Etikett** ovanför fältet, `font-weight:600`, aldrig placeholder som enda
  etikett (placeholder används som exempel-text, t.ex.
  `bestall.html`: "fornamn.efternamn@svenskakyrkan.se").
- **Hjälptext** (`.hint`) direkt under fältet, innan felet, muted-färg,
  permanent text som förklarar formatet - inte ett fel.
- **Fel** (`.field-error`, röd) står **under fältet det gäller**, inte
  samlat i en lista högst upp och inte i en alert ovanför formuläret. Ett
  formulärfel är fältets ansvar, en alert är hela handlingens status (se
  avsnitt 2). Undantag: ett fel som inte hör till ett specifikt fält (fel
  e-postserver, redan-inloggad) hör hemma i en `alert-error` - se
  `login.html`.
- Obligatoriska fält märks med en röd asterisk direkt efter etiketten
  (`bestall.html`: `E-postadress <span style="color:red">*</span>`, inline
  style - se fynd-listan för att det inte är en klass).

## 5. Rubriker och knapptexter: substantiv eller imperativ

Grundat i alla `<h1>` i kodbasen (se separat körning), mönstret är redan
konsekvent nog att skriva ner som regel:

- **En sida som VISAR en resurs eller en lista** får en substantivrubrik:
  "Mina länkar", "Alla kortlänkar", "Användare", "Tillåtna domäner",
  "Samlingar", "Tjänstestatistik", "Notisbanner".
- **En sida som BER om en handling eller bekräftar en** får en
  imperativ- eller resultatrubrik: "Logga in", "Radera ditt konto", "Skapa
  kortlänk", "Ansök om extern länkning", "Godkänn överlåtelse", eller ett
  konstaterande i perfekt när handlingen redan skett: "Kontot är raderat",
  "Överlåtelse avböjd", "Din kortlänk är aktiv!".

Regel att slå upp: **fråga vad rubriken svarar på. "Vad är det här för
sida?" → substantiv. "Vad ska jag göra / vad hände just?" → imperativ eller
perfekt particip.**

**Knapptext:** alltid imperativ, alltid verb + vad: "Skicka beställning",
"Spara ändring", "Avaktivera", "Ta bort domän", aldrig ett substantiv som
"Beställning" eller ett vagt "OK"/"Bekräfta" utan objekt. Genomgående i hela
kodbasen, ingen avvikelse hittad.

## 6. Emoji som ikoner

Emoji används på två helt olika sätt - avsiktligt olika, håll isär dem:

1. **Fasta UI-ikoner, hårdkodade som HTML-entiteter** i sekundärknappar:
   `&#128202;` (📊) framför "Statistik", `&#9998;` (✎) framför "Ändra
   mål-URL", `&#128203;` (📋) framför "Gör om till samling", `&#11015;`
   (⇩) framför "Exportera"/"PNG"/"SVG" (alla i `my_links.html`). Kontrollerat:
   **noll förekomster på `.btn-primary` eller `.btn-danger`** - emoji-ikon
   hör bara till `.btn-secondary`. Regel: **en ny sekundärknapp med ett
   tydligt piktogram-koncept (statistik, nedladdning, redigera, flytta) får
   samma emoji-som-prefix-mönster. En primär- eller farlig knapp får aldrig
   en emoji** - den ska vara entydig utan att en font behöver rendera rätt
   glyf.
2. **Fritt användarval** - en emoji-textruta där användaren själv väljer sin
   ikon: snabblänkars ikonfält (`admin/snabblänkar.html`) och
   samlingsobjektens ikonfält (`mina_samlingar_detalj.html`, dussintals
   exempel: 🚗 🚌 🙏 🔑 📧 osv). Det är innehåll, inte UI-kod, och lyder inte
   under regel 1 - användaren äger valet helt.

Skriv aldrig en ny emoji som HTML-entitet manuellt (`&#12345;`) - kopiera
tecknet rakt av som `my_links.html` gör på nyare rader, det är lika
webbläsarsäkert och lättare att läsa i diffen.

## 7. Tomma tillstånd

`.empty-state` (`style.css:288-290`) används på fyra ställen:
`admin/transfers.html`, `admin/takeover-requests.html`, `admin/users.html`,
`my_links.html`. Mönster: en stor ikon, en kort rubrik, ingen
uppmaningsknapp i standardfallet (skillnad mot t.ex. Rasmus tidigare
erfarenhet av tomma tillstånd som "invitation to act" - se avsnitt nedan).

Faktiskt textmönster:
- `admin/takeover_requests.html`: bock-ikon + "Inga väntande begäranden" +
  "Alla överlåtelsebegäranden är hanterade." - bekräftar att allt är klart,
  inte en uppmaning.
- `bundle.html` (publik samlingsvy): "Den här samlingen är tom än så länge."
  - ett konstaterande utan ikon, ingen `.empty-state`-klass.
- `admin/domanansokningar.html`: "Det finns inga väntande ansökningar." -
  samma mönster, ingen ikon.

**Regel:** ett tomt tillstånd i **admin** (någon väntar på att en kö ska
fyllas) bekräftar att kön är tom - lugnande ton, ingen call-to-action,
eftersom admin inte kan skapa nya poster i den kön själv. Ett tomt tillstånd
på en **sida användaren själv kan fylla** (en samling utan länkar, sett från
ägarens `mina_samlingar_detalj.html:` "Inga länkar ännu. Lägg till en länk
nedan.") pekar uttryckligen på knappen som löser det. Skillnaden beror på om
besökaren kan göra något åt tomheten just där. Om ja, säg vad. Om nej, säg
att det är okej som det är.

## 8. Bekräftelse före det destruktiva

Två mönster lever parallellt idag:

1. **Webbläsarens `confirm()`** - `onclick="return confirm('...')"`, 20
   förekomster: `admin/users.html`, `admin/domains.html`,
   `admin/snabblänkar.html`, `admin/transfers.html`,
   `admin/bundle_detail.html`, `delete_account_confirm.html`.
2. **Inline bekräftelsepanel** (`.confirm-overlay`, `my_links.html:39-42`,
   även i `mina_samlingar_detalj.html`) - en dold ruta som visas vid klick,
   med egen förklarande text och två knappar: farlig "Ja, avaktivera" och
   sekundär "Avbryt".

**Beslut: `.confirm-overlay` är standarden framåt, `confirm()` är
undantaget som ska fasas ut där det är enkelt.** Motivering: en
webbläsardialog går inte att styla, är lika lätt att OK:a bort av vana som
att läsa, och syns inte i skärmdumpar eller automatiska tester. En inline-
panel tvingar in bekräftelsetexten i sidans eget flöde och kan förklara
konsekvensen ("En administratör kan återaktivera den om det behövs") på ett
sätt en `confirm()`-sträng inte kan formatera. Det här är en ändring mot
nuläget - `confirm()` är i majoritet (20 mot 2 mallar) - men bara `my_links.
html` och `mina_samlingar_detalj.html` har redan gjort jobbet, så
regeln pekar dit nya destruktiva knappar ska följa efter, inte tillbaka mot
`confirm()`.

Regel oavsett mönster: bekräftelsetexten ska säga **vad som händer** och,
om det stämmer, **att det går att ångra** eller **att det inte går**. Jämför
`my_links.html`: "Länken slutar fungera direkt. En administratör kan
återaktivera den" mot `delete_account_confirm.html`: "Raderingen kan inte
ångras." Båda är rätt - tomma "Är du säker?" utan konsekvens (händer på ett
par ställen, t.ex. `admin/bundle_detail.html:137` "Flytta samlingen till ny
ägare?") ska bytas mot en mening som säger vad flytten faktiskt gör.

## 9. Mobilbrytpunkter

Tre brytpunkter finns i `style.css`, alla `max-width`, inget `min-width`:

| Brytpunkt | Rad | Gäller |
|---|---|---|
| 480px | `style.css:343` | `.miljobanner` - mindre text/padding |
| 600px | `style.css:367, 376` | `.notisbanner` och `.site-header` (nav bryter till egen rad) |
| 700px | `style.css:397` | `.admin-bar` (elva admin-länkar bryter, radnings-fix för TASK-1695-liknande problem) |

Allt annat är flex-wrap eller flödande text som klarar sig utan egen
brytpunkt - `.stats-row`, `.link-actions`, `.qr-symbolval` wrappar redan via
`flex-wrap:wrap`. **Regel: lägg inte till en ny numerisk brytpunkt för ett
enskilt element om `flex-wrap` eller `grid-template-columns: repeat(auto-fit,
minmax(...))` löser samma problem utan att hårdkoda en skärmbredd.** De tre
brytpunkter som finns löser var sitt konkret uppmätt haveri (sidledes
scroll), inte en allmän "mobilanpassning" - lägg en ny bara när du kan peka
på samma sorts trasigt läge.

**Rättat 2026-09-09.** Den här sidan påstod att inga sidor fick sidledes
scroll, och att `admin/links.html`s tabell "smalnar av korrekt" så att
Klick/Senast använd/Skapad hamnar utanför men går att scrolla. Båda
påståendena var fel, och felaktiga på ett sätt som visar att kontrollen
aldrig kördes med riktig data:

- Tabellen smalnar inte av. Den är 1211 px bred i en yta som är 1152 px
  (`main.wide` 1200 px minus padding) och därmed lika bred vid 1600 px som
  vid 1280 px. Överflödet går inte att växa ur.
- Det som hamnar utanför är inte Klick/Senast använd/Skapad utan **Åtgärder**
  - den enda kolumnen med knappar. Skillnaden är hela poängen: "lite data
  ligger utanför" mot "knapparna går inte att träffa".
- "Går att scrolla" var sant om DOM:en och falskt om användaren. Mätt:
  `.table-wrap` scrollar (`scrollWidth > clientWidth`), men scrollbarens
  höjd är **0 px** - webbläsarens overlay-scrollbar ritas inte förrän någon
  redan scrollar. Ingenting på skärmen säger att det finns mer till höger.

Uppmätt 2026-09-09 med 34 länkar och en admin-session, alltså den data
sidan faktiskt bär:

| Sida | 1280 px | 390 px | Skydd |
|---|---|---|---|
| `/admin/links` | +59 px utanför | +869 px utanför | `.table-wrap` |
| `/admin/bundles` | ryms | +621 px utanför | **inget** - `overflow-x: hidden` på föräldern |
| `/admin/domaner` | ryms | +410 px utanför | `.table-wrap` |

`/admin/bundles` var värst: innehållet låg utanför bakom `overflow-x: hidden`
och gick alltså inte att nå alls på en telefon.

Efter att avsnitt 10 tillämpats, samma data och samma bredder:

| Sida | 1280 px | Högsta radhöjd, 1280 px | Högsta radhöjd, 390 px |
|---|---|---|---|
| `/admin/links` | ryms (1152/1152) | 44 px (var 62) | - |
| `/admin/bundles` | ryms | oförändrad | oförändrad |
| `/admin/domaner` | ryms (852/852) | 62 px (var 103) | 84 px (var 166) |

Sidledes svep står kvar på telefonen, nu med synlig toning. Radhöjden är den
stora vinsten: en cell som slutar brytas till två rader ger tillbaka mer på
en lista med 34 poster än de pixlar den kostar i bredd. Att `/admin/domaner`
blev 34 px bredare på 390 px är den avvägningen, gjord med öppna ögon.

Övriga adminsidor (`users`, `takeover-requests`, `transfers`, `stats`,
`snabblänkar`) renderade ingen tabell med den testdatan och är därför
**inte mätta** - inte samma sak som mätta och felfria.

## 10. Tabeller: bredd, kolumner och åtgärder

Avsnitt 3 avgör *om* något ska vara en tabell. Det här avgör vad tabellen
får innehålla när den är det. Reglerna kommer ur mätningen i avsnitt 9, inte
ur smak.

### Budgeten

Adminsidorna kör `main.wide` (`style.css:46`), alltså **1200 px minus 48 px
padding (`style.css:41`) = 1152 px användbar bredd**. Det är ett tak och inte ett riktvärde: en bredare skärm
ger inte mer plats. Räkna innan du lägger till en kolumn.

**Regel: en tabell får aldrig vara bredare än sin yta på den bredd den är
byggd för.** Att `.table-wrap` finns är ingen ursäkt - dess scrollbar är en
overlay som ritas först när någon redan scrollar, alltså osynlig för den som
inte vet att det finns mer. Ett `overflow-x: auto` är en räddning för
telefonen, inte en plats att lägga en knapp på.

### Åtgärdskolumnen

**Regel: högst tre åtgärder per rad, och den bredaste tänkbara varianten är
den som räknas.** `admin/links.html` bär Detalj + QR + en tredje som växlar
mellan `Avaktivera`, `Återaktivera` och `📋 Se samling` - det är den längsta
av dem som sätter kolumnbredden för hela tabellen, inte den vanligaste.

Behövs en fjärde åtgärd hör den hemma på detaljsidan. Bygg ingen meny: det
mönstret finns inte någon annanstans i gränssnittet, och en meny som bara
existerar på ett ställe blir en egen sak att lära sig.

`td.actions` behåller `white-space: nowrap` - knappar som bryter mitt i ett
stråk är svårare att träffa än knappar som tvingar fram ett val om vad som
ska bort.

### Vad som får kortas, och hur

Tre olika beteenden levde parallellt i `admin/links.html`: Mål-URL kortades
med ellips, Ägare bröt till två rader, och Skapad bröt datum från tid medan
Senast använd inte gjorde det. Det är inte tre beslut, det är noll beslut.

**Regel, i den ordning man ska pröva dem:**

1. **Slå ihop innan du kortar.** Två kolumner som svarar på samma fråga blir
   en. Senast använd och Skapad är båda "när hände något med den här
   länken" - visa den senaste händelsen och lägg den andra i `title`.
2. **Korta det som har en igenkännbar början.** En e-postadress känns igen
   på namnet före `@`, en URL på sitt värdnamn. Visa den delen, lägg hela
   värdet i `title`. Aldrig ellips i mitten.
3. **Låt aldrig en cell bryta till två rader för att spara bredd.** En rad
   som är dubbelt så hög kostar mer på en lista med 34 poster än de 40 px
   den sparar i sidled.
4. **Datum skrivs `YYYY-MM-DD HH:MM` på en rad, eller inte alls.** Bryts det
   över två rader är kolumnen för smal och något annat ska bort först.

### Mobil

**Regel: varje tabell ligger i `.table-wrap`.** `admin/bundles.html` gjorde
inte det och hamnade bakom `overflow-x: hidden` på föräldern - 621 px
innehåll som inte gick att nå alls på en telefon. En tabell utan wrap är en
bugg, inte ett val.

**Regel: att det finns mer i sidled ska SYNAS.** Wrapen ensam räcker inte -
overlay-scrollbaren ritas först när någon redan scrollar, och den som inte
vet att det finns mer får aldrig veta det. `app/static/tabellsvep.js` sätter
`data-mer="hoger|vanster|bada"` på wrapen, och `style.css` tonar ut
innehållet i den kanten med en mask.

Mönstret är hämtat från slöjda.de, tillsammans med dess dyrköpta slutsats:
**en skugga bakom innehållet fungerar inte.** Celler med egen bakgrund - våra
`.badge`-pillar i statuskolumnen - målar över skuggan precis där den behövs.
Masken ligger därför på behållarens box, inte på det som skrollar, så
toningen står stilla i kanten medan innehållet glider förbi och träffar även
pillren. Skriptet är rent tillägg: utan det sätts inget attribut, ingen mask
läggs på, och tabellen fungerar som förut.

Skriptet laddas globalt från `base.html`. Det gör ingenting på en sida utan
`.table-wrap`, och det är billigare än att komma ihåg det i varje ny mall.

Sidledes svep är alltså svaret på telefonen, inte en nödlösning på väg mot
något annat. Ett kort per rad (avsnitt 3) hör hit först när raden behöver
egna dolda paneler - inte för att en tabell är bred.

### Att kontrollera en tabelländring

Widderna ljuger om man mäter dem på tom data. Mät med den mängd rader sidan
faktiskt bär, som admin, och jämför `table.scrollWidth` mot ytans
`clientWidth` vid **både 390 px och 1280 px**. Klicka sedan varje åtgärd i
en rad: ett `<form style="display:inline">` i en cell är precis där en
omstrukturering slutar posta utan att synas. Öppna också en dold rad
(QR-raden i `admin/links.html`), för dess `colspan` ska stämma med antalet
`<th>` och gör det tyst fel annars.

Kontrollera toningen genom att sätta `scrollLeft` till 0, mitten och slutet
och läsa `data-mer`: `hoger`, `bada`, `vanster`. Ryms tabellen ska attributet
inte finnas alls.

## Bilaga: knapp- och komponentreferens

| Klass | Rad i style.css | Används för |
|---|---|---|
| `.btn-primary` | 186 | En handling per formulär, sidans huvudsyfte |
| `.btn-secondary` | 188 | Allt annat som inte förstör något |
| `.btn-danger` | 190 | Ta bort / avaktivera / radera |
| `.btn-sm` | 192 | Knappar inne i ett kort eller en tabellrad |
| `.alert-success/-warning/-error/-info` | 205-208 | Svar på en handling |
| `.card` | 127 | Enskilt formulär eller enhet att agera på |
| `.badge-*` | 242-245 | Statuspunkt kopplad till `LinkStatus` |
| `.empty-state` | 288 | Tom lista/kö, se regel i avsnitt 7 |
| `.form-group` / `.hint` / `.field-error` | 140-148 | Formulärfält, se avsnitt 4 |

---

# Fynd som inte hör hemma i specen

Observationer och inkonsekvenser, inte åtgärdade. Fil och radnummer där det
går att peka exakt.

1. **Inline `style=`-attribut**: `mina_samlingar_detalj.html` har **101**
   förekomster, `my_links.html` **73** (Rasmus nämnde 93/74 - mätt nu till
   101/73, skillnaden är sannolikt tillväxt sedan senaste mätning). Den
   absoluta merparten sätter samma tre-fyra deklarationer om och om igen
   (`style="font-size:.82rem; color:var(--muted);"` m.fl.) som redan finns
   som klasser (`.hint`, `.link-meta`) någon annanstans i samma fil.
2. **`extra_style`-block**: **33 mallar** har ett eget `{% block
   extra_style %}` vid sidan av `style.css` (fler än de 20 Rasmus nämnde -
   färskt antal). Flera av dem duplicerar exakt samma regler mellan filer,
   t.ex. h1 med `font-size:1.4rem; color:var(--blue-dark); margin:0;`
   upprepas inline eller i extra_style i minst sex admin-mallar
   (`admin/domains.html:43`, `admin/bundles.html:43`, `admin/users.html:84`,
   `admin/snabblänkar.html:177`, `admin/stats.html:49`) i stället för att
   ligga en gång i `.page-title h1` (`style.css:268`), som redan finns och
   gör exakt det.
3. **`.link-card` (my_links.html:6-9) duplicerar `.card`** (style.css:
   127-133) fält för fält (background, border, border-radius, padding,
   box-shadow) under ett eget klassnamn i stället för att komponera på
   `.card`. Samma mönster troligen i fler list-kort - inte fullständigt
   inventerat.
4. **Två bekräftelsemönster för destruktiva handlingar** lever parallellt,
   se avsnitt 8: `confirm()` (20 mallar) mot `.confirm-overlay` (2 mallar).
5. **Tomma bekräftelsetexter utan konsekvens**: `admin/bundle_detail.
   html:137,145` ("Flytta samlingen till ny ägare?", "...till dig själv?")
   och `admin/snabblänkar.html:494` ("Ta bort introtexten?") säger inte vad
   som händer efteråt, till skillnad från motsvarande text i `my_links.
   html:277-278`.
6. **`hjalpruta`** (`admin/om_edit.html:33-34,50`) är i praktiken en egen
   komponent (egen font-storlek, egen `code`-styling) som råkar ärva
   `alert-info`s färg via en extra klass i samma attribut. Inte fel, men
   inkonsekvent med hur andra mallar bara skriver text direkt i sin `.alert`.
7. **Asterisk för obligatoriska fält** sätts med inline `style="color:red"`
   (t.ex. `bestall.html`, sök på `*</span>`) i stället för en klass - `--red`
   redan definierad som variabel men inte återanvänd här.
8. **Testdata-bugg, inte ett UI-fel**: kortlänkarna `kollekt` och `gava` i
   testdatabasen pekar på `https://svky.se/kollekt` respektive
   `https://svky.se/gava` - alltså sig själva - i stället för på
   Swish-generatorns `/swish?mottagare=...`-adress. `GET /kollekt` ger
   därför en riktig 302 till en extern adress som i sin tur svarar med
   produktionens 404-sida (samma mall, annan miljö) när den nås utifrån.
   Ingen kodbugg, men värt att känna till om någon annan skärmdumpar samma
   testdata och undrar varför "Swish-länken" ger 404.
9. **`RESERVED_CODES`** (`app/config.py:40`) och de faktiska route-modulerna
   har vuxit isär från beskrivningen i projektets `CLAUDE.md`
   (`app/routes/user.py` och `app/routes/public.py`s ansvar är idag uppdelat
   på `app/routes/user/*.py`, `app/routes/orders.py`,
   `app/routes/swishgenerator.py`, `app/routes/takeovers.py`,
   `app/routes/transfers.py`). Utanför den här uppgiftens scope att fixa,
   men CLAUDE.md:s filstruktur-avsnitt stämmer inte längre med repot.
