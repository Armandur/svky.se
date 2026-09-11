# Swish-applänkens odokumenterade format

`swish://payment?data=<URL-kodad JSON>` - vad som faktiskt fungerar, mätt på en
riktig telefon i september 2026.

*English version: [swish-app-link-format.md](#file-swish-app-link-format-md)*

> **Swish dokumenterar inte det här formatet.** Deras utvecklardokumentation
> beskriver bara `swish://paymentrequest?token=…&callbackurl=…`, som kräver
> token ur Handel-API:t, certifikat och ett handelsavtal. Formen
> `payment?data=` nedan är community-kunskap. Den fungerar i dag, men
> ingenting garanterar att den fortsätter göra det.

## Varför sidan finns

Flera öppna projekt bygger den här länken, och de är oense om detaljerna. Två
ofta kopierade implementationer skickar `version` som sträng. Två andra skickar
tal. Vi körde strängformen i drift, och den slutade tyst fylla i betalningen.
Appen öppnades till en tom skärm.

Så vi mätte. Varje tabell nedan är ett observerat utfall från att trycka på en
länk i en telefon med ett riktigt Swish-nummer, inte en läsning av någon
specifikation.

## Kortaste svaret

```json
{
  "version": 1,
  "payee":   {"value": "1231234567"},
  "amount":  {"value": 149.5},
  "message": {"value": "Faktura 1042"}
}
```

Gör JSON till en sträng, URL-koda hela strängen, och lägg den efter
`swish://payment?data=`. Det är formatet vi kör i dag.

> **BÅDA formaten fungerar i dag.** `swish://payment?data=` är det vi kör,
> och Swish eget https-format fungerar lika bra - som tryckt länk, som skannad
> kod, och till skillnad från C-formatet även i telefonens kamera:
> `https://app.swish.nu/1/p/sw/?sw=1231234567&amt=100&cur=SEK&msg=Testkod`
> Båda prövade på telefon 2026-09-10, se mätning 6. Vi har inte bytt: koden
> blir fyrtio procent bredare. Det är ett val, inte en begränsning.

> **`"version": "1.0"` bryter länken.** Appen öppnas men fyller inte i
> någonting. Det måste vara *talet* `1`. Det var den enda skillnaden mellan en
> länk som fungerade och en som inte gjorde det.

## Mätning 1: vilken form fyller i betalningen

Sex former, samma telefon, samma riktiga Swish-nummer.

| Form | Utfall |
| --- | --- |
| `version` och `amount` som tal | Fungerar. Betalvy, fälten låsta |
| samma, `payee` också som tal | Fungerar |
| samma, plus `"editable": false` överallt | Fungerar |
| **allt som strängar, `"version": "1.0"`** | **Appen öppnas, inget ifyllt** |
| `version` som tal, `amount` som sträng | Fungerar |
| bara `payee`, inget belopp | Fungerar. Appen frågar om belopp |

`amount` tål både ett tal och en numerisk sträng. `version` tål inte en sträng.

## Mätning 2: belopp med ören

| Skickat värde | Utfall |
| --- | --- |
| `"amount": {"value": 1.15}` | Fungerar, visar 1,15 kr |
| `"amount": {"value": "1.15"}` | Fungerar |
| `"amount": {"value": "1,15"}` | **Fungerar inte** |

**Decimalpunkt, aldrig komma**, trots att svensk notation och QR-kodens
nyttolast båda använder komma. De två formaten ser lika ut och är det inte,
vilket är ett lätt fel att skriva och ett svårt att upptäcka.

## Mätning 3: fritt belopp (gåva)

För en gåva där betalaren väljer summan är svaret att **utelämna nyckeln
helt**.

| Form | Utfall |
| --- | --- |
| `"amount": {"value": "", "editable": true}` | Fungerar inte |
| `"amount": {"value": ""}` | Fungerar inte |
| `"amount": {"value": null, "editable": true}` | Fungerar inte |
| **ingen `amount`-nyckel, `message` kvar** | **Fungerar. Tomt beloppsfält, meddelandet kvar** |
| ingen `amount`, `message` fritt | Fungerar |
| `"amount": {"value": "0", "editable": true}` | Öppnas, men tvingar betalaren att ändra från noll och varnar att en krona är minsta belopp |

```json
{
  "version": 1,
  "payee":   {"value": "1231234567"},
  "message": {"value": "Gåva"}
}
```

## Mätning 4: mottagaren går inte att låsa

Det här är fyndet med verkliga följder.

`"editable": true` låter betalaren ändra ett fält. Utan nyckeln är fältet låst,
och `"editable": false` accepteras men behövs inte. Så långt som väntat.

**Men så fort något fält bär `editable: true` går mottagarnumret att ändra
också** - oavsett vad `payee` själv säger. Sex former provades, inklusive
`"editable": false` uttryckligen på `payee`. Ingen av dem höll numret låst.
Bara en helt låst länk gör det.

| Form | Går numret att ändra? |
| --- | --- |
| Allt låst | Nej |
| Belopp fritt, `payee` uttryckligen `"editable": false` | **Ja** |
| Belopp fritt, `payee` utan nyckel | **Ja** |
| Meddelande fritt, `payee` uttryckligen låst | **Ja** |
| Belopp fritt, ingen `message`-nyckel alls | **Ja** |

En applänk med fritt belopp låter alltså den som öppnar den peka om
betalningen till ett annat nummer. På en kod som trycks på en affisch eller
en faktura är det inte en skönhetsfläck.

**Rättelse 2026-09-08: den skannade QR-koden beter sig likadant.** Sidan
påstod först att QR-kodens låsmask höll där applänkens inte gjorde det. Den
gör inte det. Skannar man en kod med låst mottagare men fritt belopp går
numret att byta i appen, precis som via applänken. Låsmasken styr vilka fält
appen öppnar för redigering - den fäster inte mottagaren. Mätt på telefon.
Det tidigare påståendet var aldrig prövat för QR-vägen utan följde med som
antagande.

**Tillägg 2026-09-11: låsmask 1 gör mottagaren fri, och bara den.** Det
fallet saknades i tabellen ovan. En kod med `C…;1,00;…;1` - alltså bara
mottagaren fri, belopp och meddelande låsta - låter betalaren byta nummer
medan de två andra fälten står kvar låsta. Kryssrutan "Mottagaren får ändras"
gör alltså något, men bara i det här enda läget. Så fort belopp eller
meddelande är fritt släpper mottagaren ändå. Mätt på telefon.

Vad som följer av det:

- **Ingenting håller mottagaren låst utom att låsa alla fält.** Det gäller
  den tryckta koden lika mycket som applänken.
- Den som skapar en kod ska få veta vad den tillåter, för de värden hen
  fyllt i. En rad som räknar upp kryssrutorna räcker inte: mottagaren går
  att ändra utan att någon kryssat i den, och en text som säger något
  annat säger emot verkligheten på just den punkt som betyder mest.
- Det är en **upplysning, inte en varning**. Betalaren kan bara peka om sin
  egen betalning, ser mottagaren innan hen skriver under med BankID, och
  har sällan skäl att flytta en kollekt till sig själv. Vid försäljning på
  plats kontrollerar säljaren ändå att betalningen kommit fram, i
  Swish-appen eller på kontot - och det gör man oavsett hur koden är låst.
- En helt låst kod är säker i båda formerna.

## Mätning 5: app.swish.nu öppnar appen, men bär inte formatet

> **RÄTTAD AV MÄTNING 6.** Slutsatsen nedan - att domänen inte duger för en
> förifylld betalning - gällde en fråga vi ställde fel. Vi provade
> `app.swish.nu` med VÅRT `?data=<JSON>`. Domänen bär ett annat format, och
> med det fungerar den. Läs mätning 6 innan du bygger något på det här
> avsnittet.

Frågan var om `swish://` kan bytas mot en vanlig https-adress. En egen
URI-scheme gör ingenting alls när appen saknas - ingen sida, inget besked -
och flera appar och webbvyer vägrar öppna okända scheman, så en länk i ett
utskick kan vara död utan att avsändaren ser det.

**Domänen finns och är riktig.** `app.swish.nu` är registrerad som Universal
Link på iOS och App Link på Android, för `se.bankgirot.swish` - skarpa Swish,
inte en testapp. Hämtat 2026-09-09:

| Fil | Innehåll |
| --- | --- |
| `/.well-known/apple-app-site-association` | `appID: 7PQRK67B3Y.se.bankgirot.swish`, `paths: ["/", "*"]` |
| `/.well-known/assetlinks.json` | `package_name: se.bankgirot.swish`, `handle_all_urls` |

Utan appen serverar domänen en "Ladda ner Swish"-sida med länkar till App
Store och Google Play.

**Men den bär inte vårt format.** Mätt på telefon 2026-09-09 med fyra
sökvägar - `/payment`, `/`, `/1/p/` och `/paymentrequest`, alla med samma
`?data=<URL-kodad JSON>` som `swish://` använder:

> Swish öppnades, men tomt. Inget belopp, inget meddelande, ingen mottagare.

Universal Link-kopplingen fungerar alltså - appen startar - men
`?data=`-nyttolasten når den inte. Domänen duger inte för en förifylld
betalning.

**Följden: `swish://payment?data=` står kvar.** Den är sämre på fallback men
den enda form som faktiskt fyller i fälten.

**Kvar som möjlighet:** eftersom `app.swish.nu` visar "Ladda ner Swish" bara
när appen saknas, och öppnar appen när den finns, duger den som en
*kompletterande* länk för den som inte har Swish - vid sidan av `swish://`
för själva betalningen. Det är inte byggt, och är ett eget beslut.

## Mätning 6: formatet finns, och det är Swish eget

Mätt 2026-09-10, sedan Swish egen QR-generator på
<https://www.swish.nu/marknadsmaterial/qr-generator> avslöjat vad den
producerar. Deras generator ritar ingen kod i webbläsaren: den POSTar till
`https://api.swish.nu/qr/v2/prefilled` och får tillbaka en färdig bild. Vi
körde generatorn, fångade svaret och avkodade det.

**Deras officiella kod bär en https-adress, inte C-formatet:**

```
https://app.swish.nu/1/p/sw/?sw=1231234567&amt=100&cur=SEK&msg=Testkod&src=qr
```

Sökvägen är `/1/p/sw/` och parametrarna heter `sw`, `amt`, `cur` och `msg`.
Mätning 5 provade `/1/p/` med `?data=` - alltså nästan rätt sökväg och helt
fel parametrar. Det är därför appen öppnades tom.

**Låsningen styrs av `edit`**, en kommaseparerad lista över vad som är
REDIGERBART. Utelämnad betyder att allt är låst. Uppmätt genom att generera
alla kombinationer via deras API och avkoda bilderna:

| Vad som ska vara fritt | Parameter |
| --- | --- |
| ingenting | *(ingen `edit`)* |
| meddelandet | `edit=msg` |
| beloppet | `edit=amt` |
| båda | `edit=amt,msg` |

Samma innebörd som vår låsmask, alltså satt betyder redigerbar - men som namn
i stället för bitar.

**Mottagaren går inte att öppna.** API:t kräver att `payee` är en sträng och
avvisar ett objekt med `editable`. Det finns ingen `edit=sw`. Vår
`REDIGERBAR_MOTTAGARE` har alltså ingen motsvarighet här. Det stod först här
som en slutsats dragen ur vad API:t vägrar ta emot, alltså ur vad Swish egen
generator gör. Mätning 7 prövade det på telefon i stället, och det höll.

**Utan belopp utelämnas `amt` helt**, precis som `applank()` utelämnar
`amount` för en gåva med fritt belopp.

**Prövat på telefon 2026-09-10**, både som skannad kod och som tryckt länk,
i alla tre låslägena:

| Läge | Går att ändra i appen |
| --- | --- |
| ingen `edit` | ingenting, mottagaren inräknad |
| `edit=amt` | beloppet OCH mottagaren |
| `edit=amt,msg` | alla tre |

**Regeln är alltså densamma som för vårt eget format:** så fort något fält är
fritt går mottagaren att peka om, och bara en helt låst betalning håller
numret. Se mätning 4. Att den gäller lika för skannad kod och tryckt länk är
mätt, inte antaget - knapparna betedde sig som koderna, prov för prov.

**Kameran öppnar den.** Det är en vanlig https-adress, så telefonens
kameraapp läser den och Universal Link-kopplingen tar den vidare till Swish.
Det är hela skillnaden mot C-formatet, som bara Swish-appens egen skanner
förstår - och orsaken till en felanmälan 2026-09-10 där en användare trodde
att koderna slutat fungera.

**Vad det kostar.** URL-formatet är längre, alltså blir matrisen tätare:

| Format | Tecken | Moduler vid M | Moduler vid H |
| --- | --- | --- | --- |
| `C…` (vårt) | 30 | 37 | 41 |
| URL (Swish eget) | 79 | 45 | 57 |

Swish-symbolen i mitten kräver H. Där är URL-varianten 1,39 gånger bredare:
en kod som i dag trycks 30 mm behöver 42 mm för samma modulstorlek. Det är
avvägningen mellan de två, och den är verklig för den som trycker på papper.

**Vad vi kör i dag:** `swish://payment?data=` för knappen och `C…` för koden.
Båda fungerar. URL-formatet skulle kunna ersätta båda med EN sträng, och
dessutom göra koden läsbar i kameran - mot fyrtio procent större kod.

## Mätning 7: `edit` tål bara sina två namn

Mätt 2026-09-11 på telefon, med ett riktigt Swish-nummer och en krona i
belopp. Frågan var om mätning 6 hade rätt om mottagaren. Det påståendet vilade
på att generator-API:t avvisar ett `payee`-objekt, alltså på vad Swish egen
generator gör. Vad appen tål är en annan fråga, och hela `payment?data=` är ett
exempel på att de två inte är samma sak.

Kontrollerna först. Utan dem betyder ingen av raderna något:

| Rad | Skickat | Utfall |
| --- | --- | --- |
| R1 | ingen `edit` | Fylls i. Allt låst, mottagaren inräknad |
| R2 | `edit=amt` | Fylls i. Belopp och mottagare fria |

Båda som mätning 6 sade. Sedan de fyra kandidaterna:

| Rad | Skickat | Utfall |
| --- | --- | --- |
| R3 | `edit=sw` | **Appen öppnas, inget ifyllt** |
| R4 | `edit=sw,msg` | **Appen öppnas, inget ifyllt** |
| R5 | `edit=payee` | **Appen öppnas, inget ifyllt** |
| R6 | `edit=all` | **Appen öppnas, inget ifyllt** |

**Ett okänt värde i `edit` bryter hela betalningen.** Appen startar, men
belopp, meddelande och mottagare är tomma. Den hoppar alltså inte över det den
inte känner igen.

R4 visar hur långt det går. Där stod ett känt namn bredvid ett okänt, och
`msg` räddade ingenting. Ett enda okänt namn fördärvar listan.

Två saker följer av det:

- **Mottagaren går inte att öppna, och nu är det mätt.** Varken `sw` eller
  `payee` finns, och `all` finns inte heller. `REDIGERBAR_MOTTAGARE` har ingen
  motsvarighet i URL-formatet. Generatorn döljer därför kryssrutan för
  mottagaren när URL-formatet är valt.
- **`edit` är en fälla för den som bygger vidare.** Lägger någon till ett
  fältnamn i listan slutar koden tyst att fylla i något. Den ritas, den
  skannas, appen öppnas - och betalningen är tom. `url_strang()` skickar bara
  `amt` och `msg`, och den gränsen ska stå kvar.

Symptomet är detsamma som i mätning 5, och det är lika lätt att missa: koden
ser riktig ut hela vägen fram till att någon ska betala.

**Mellanslag får kodas som plus.** `url_strang()` bygger frågesträngen med
`urlencode`, som gör mellanslag till `+` och inte `%20`. Appen läser plus som
ett mellanslag: `msg=Prov+plus` visas som "Prov plus", precis som `%20`-
tvillingen. Mätt 2026-09-11. Det var värt att pröva, för raderna ovan
skickade `%20` medan koden i drift skickar `+`, och Swish eget exempel har
inget mellanslag att jämföra med.

## Vad Swish själva dokumenterar

Deras guide "Trigger the Swish app" på
developer.swish.nu beskriver bara `swish://paymentrequest?token=<token>&callbackurl=<url>`.
Det tokenet kommer från Handel-API:t och kräver avtal och certifikat, alltså
inte vårt fall. Formatet på den här sidan står fortfarande ingenstans hos
Swish - det är härlett ur appen.

## QR-kodens nyttolast är ett annat format

Blanda inte ihop dem. Den skannade koden bär en sträng med semikolon, inte
JSON, och den använder komma för decimaler där applänken använder punkt.

```
C<mottagare>;<belopp>;<URL-kodat meddelande>;<låsmask>

C1237856901;100,00;12229445;0
```

| Fält | Anmärkning |
| --- | --- |
| `C` | Obligatoriskt prefix |
| `mottagare` | Bara siffror, tio tecken |
| `belopp` | Två decimaler, decimal**komma**: `100,00` |
| `meddelande` | URL-kodat. Appen visar och sparar 50 tecken, medan API-schemat tillåter 70. Den snävare gränsen är den som gäller |
| låsmask | Decimal bitmask: mottagare 1, belopp 2, meddelande 4. Satt bit betyder *redigerbar*, alltså tvärtom mot vad namnet antyder. Utelämnad mask läses som 0 och låser allt |

Tomma fält behålls som tomma strängar mellan semikolonen: `C1231234567;;;6`.

### Att rita koden

- Felkorrigering **H**. Swish-symbolen täcker mitten, och en tryckt kod
  samlar smuts och slitage.
- Symbolen på **25 %** av kodens bredd, räknat mot koden *utan* den tysta
  zonen. Räknat mot hela bilden blir symbolen 31 % av koden, nära vad H klarar.
- **Ingen vit platta bakom symbolen.** Swish logotypfil bär redan sin egen
  runda vita bakgrund, och deras riktlinjer förbjuder att lägga en till ovanpå.
- Designen i avsnitt 5 av specifikationen v1.7.2 (prickmönster, lila gradient,
  avkapat hörn) är **utgången**. Swish egen nuvarande generator ger vanliga
  svartvita koder med den runda symbolen.

**Nedskalningen av symbolen har en fälla.** PNG-filer bär ofta svart i
färgkanalerna där de är helt genomskinliga, eftersom värdet ändå inte syns.
LANCZOS interpolerar färg och alfa var för sig, så en rak nedskalning blandar
in den svärtan i kantpixlarna och ger en mörk frans runt symbolen. Multiplicera
färgen med alfa *före* skalningen, och komponera sedan för hand:
`under × (1 − alfa) + färg`. En vanlig paste med alfamask räknar in alfa två
gånger och blir för mörk.

## Kontrollera avläsningen, inte renderingen

En kod som ritas vackert och inte går att skanna är det fel som når tryck.
Avkoda varje genererad kod i proven.

OpenCV:s `QRCodeDetector` duger inte som ensam domare. Vi fann att den faller
på vissa H-kodade matriser *helt utan symbol i mitten*. Tolv av fjorton
misstänkta koder föll innan någon symbol lagts på.
[zxing-cpp](https://github.com/zxing-cpp/zxing-cpp) läste alla 472
kombinationerna felfritt. Använd en andra avkodare, annars felsöker du problem
som inte är dina.

## Implementationer, och var de skiljer sig

| Projekt | `version` | `amount` |
| --- | --- | --- |
| [swish-easy](https://github.com/mast4461/swish-easy) | tal | tal |
| [ruby_swish_qr](https://github.com/linuscorin/ruby_swish_qr) | tal | tal |
| Diverse kopior i omlopp | sträng `"1.0"` | sträng |

Talformen är den som fungerar. Har du ärvt kod som använder strängar kan den ha
fungerat en gång, som vår gjorde, och den gör det inte nu.

---

Mätt 2026-09-08 på en fysisk enhet med ett riktigt Swish-nummer, under bygget
av en QR-kodsgenerator. Varje utfall ovan är en observation, inte ett citat. Formaten kan ändras utan förvarning,
eftersom inget av det här dokumenteras av Swish.

Källor: [swish-easy](https://github.com/mast4461/swish-easy),
[ruby_swish_qr](https://github.com/linuscorin/ruby_swish_qr),
[Swish utvecklardokumentation om att öppna appen](https://developer.swish.nu/documentation/guides/trigger-the-swish-app),
och *Guide Swish QR code design specification* v1.7.2 avsnitt 6.1.
