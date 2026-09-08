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
`swish://payment?data=`.

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

Vad som följer av det:

- **Ingenting håller mottagaren låst utom att låsa alla fält.** Det gäller
  den tryckta koden lika mycket som applänken.
- Varje kod med ett fritt fält ska bära en varning där någon skapar den,
  QR-koden inräknad.
- En helt låst kod är säker i båda formerna.

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
