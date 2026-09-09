# Backlog Export

## [P2][done] [svky] Inloggade får Förbjudet på alla skanner-säkra engångslänkar

## Context

GET-handlern för en engångslänk signerar CSRF-token med anon-hemligheten (get_anon_csrf_secret), medan POST-handlern validerar med get_csrf_secret(), som prioriterar sessionens hemlighet före csrf_anon-cookien. Finns en sessionscookie jämförs alltså två olika hemligheter, och POST:en faller på 403 med texten Förbjudet.

Bekräftelsesidan visas som den ska. Felet kommer först när knappen trycks, vilket gör det svårt att förstå för användaren.

Det drabbar precis de flöden som granskningen 2026-08-20 gjorde skanner-säkra:

- GET /verify/{token} (app/routes/orders.py:442)
- GET /auth/{token} (app/routes/auth.py:130)
- GET /login (app/routes/auth.py:36)
- GET /transfer-action/{token} (app/routes/transfers.py:129)
- GET /mina-samlingar/overlatelse/{token} (app/routes/user/bundles.py:1015)
- GET /mina-samlingar/overlatelse/{token}/decline (app/routes/user/bundles.py:795)

## Mätt 2026-09-07

Mot dev och mot en lokal instans, samma verify-token seedad två gånger:

- Utloggad besökare: POST /verify/<token> gav 200, länken aktiverades.
- Samma flöde med en giltig sessionscookie: POST gav 403.
- Rasmus bekräftade oberoende att verifiering fungerar i privat fönster men inte i det inloggade.

## Implementation hints

GET-handlern ska lösa hemligheten i samma ordning som POST gör. Ungefär:

    secret = get_csrf_secret(request)
    is_new = False
    if not secret:
        secret, is_new = get_anon_csrf_secret(request)

Att bara sluta skicka csrf_secret i kontexten räcker INTE - då renderas tom sträng för en utloggad besökare utan csrf_anon-cookie, vilket är felet i TASK-1679.

Hör ihop med TASK-1679, som är samma familj: där saknas anropet helt i takeovers.py.

## Acceptance criteria

- [ ] Alla sex GET-handlers löser hemligheten i samma ordning som POST-handlern
- [ ] En inloggad användare kan verifiera en kortlänk, använda en magic link och godkänna en överlåtelse
- [ ] En utloggad användare kan fortfarande göra samma sak
- [ ] Skanner-skyddet är kvar: GET ändrar fortfarande inget tillstånd

## Verification

- Prov per route, i två varianter: med och utan sessionscookie. Båda ska ge samma utfall som utloggad ger i dag
- Proven ska FALLA mot dagens kod i den inloggade varianten
- Manuellt: verifiera en länk i ett fönster där du redan är inloggad

- ID: `01M1XX94HNAC16F69FK60JHRHX`
- Type: bug
- Actor: human:rasmus

---

## [P2][done] [svky] Utloggade kan inte begära övertagande: formuläret renderar tomt CSRF-token

## Context

takeover_form (GET /request/takeover) sätter aldrig anon-CSRF-cookien och skickar inget csrf_secret i template-kontexten. Jinja-globalen i app/main.py:74 letar då i ordningen kontext, sessionscookie, csrf_anon-cookie, hittar ingenting och returnerar tom sträng. Formuläret får value="", och POST:en faller på 403.

Det gör flödet obrukbart för precis den grupp det finns till för: någon utanför som vill ta över en länk vars ägare slutat. Inloggade märker inget, för de har csrf_secret i sessionen.

app/routes/takeovers.py är den enda route-filen som varken importerar eller anropar get_anon_csrf_secret och set_anon_csrf_cookie. orders.py, auth.py, transfers.py och user/bundles.py gör alla det.

## Mätt 2026-09-07

Mot en instans med aktuell main:
- Färsk besökare direkt till /request/takeover: renderat token tomt, ingen csrf_anon-cookie satt, POST gav 403.
- Besökare som hämtat / först: samma resultat, 403. Startsidan sätter heller ingen anon-cookie.

## Acceptance criteria

- [ ] GET /request/takeover anropar get_anon_csrf_secret och set_anon_csrf_cookie, som orders.py gör
- [ ] Samma sak för GET /request/bundle-takeover (app/routes/takeovers.py, runt rad 177)
- [ ] En utloggad besökare som går direkt till /request/takeover kan skicka in formuläret
- [ ] Inloggade påverkas inte, deras token kommer fortsatt från sessionen

## Verification

- Prov som hämtar GET /request/takeover med tom cookiejar, plockar csrf_token ur svaret och POST:ar. Ska inte ge 403. Provet ska FALLA mot dagens kod
- Samma prov för bundle-varianten
- curl -sS -c jar URL/request/takeover | grep csrf_token: value får inte vara tom

- ID: `01M1XWGZPW9NATXHAHRKJ65XTK`
- Type: bug
- Actor: human:rasmus

---

## [P2][done] [svky] Lägg grunden till en testsvit och täck säkerhetsfixarna

## Context

Repot har ingen testsvit alls: inga tests/, inga test_*.py, ingen pytest i requirements.txt. Säkerhetsgranskningen 2026-08-20 gav tio commits som alla verifierades med engångsskript i en scratchpad. De skripten är borta vid nästa session, så ingenting hindrar att felen kommer tillbaka.

Två av fynden är precis den sorten som en regressionsprov hade fångat direkt: POST /admin/takeover-action saknade admin-kollen som GET hade, och check_rate_limit jämförde en ISO-sträng mot ett SQL-datum så räknaren alltid blev noll.

Uppgiften är att lägga grunden - fixturer och körbar svit - och täcka de fixarna, inte att nå någon täckningsgrad.

## Acceptance criteria

- [ ] pytest och httpx ligger i requirements.txt (eller en requirements-dev.txt som README pekar ut)
- [ ] tests/conftest.py ger en fixtur med FastAPI TestClient mot en tom SQLite-databas per prov, via DATABASE_PATH i tmp_path. Inga prov får röra data/links.db
- [ ] Fixturer för inloggad användare och för admin, så ett prov kan anropa en skyddad route
- [ ] POST /admin/takeover-action/<token> utan admin-session ger 303 till /login och flyttar INTE ägandet. Gäller både kind=link och kind=bundle
- [ ] Samma route med giltig admin-session utför åtgärden. Utan detta prov kan spärren vara för hård utan att någon märker det
- [ ] check_rate_limit släpper igenom RATE_LIMIT_PER_HOUR anrop och nekar det därpå följande. Ett prov måste falla om jämförelsen görs mot en ISO-sträng i stället för datetime('now')
- [ ] Rate limit-hinkarna är åtskilda per nyckel: två olika ip-värden delar inte hink
- [ ] Längdgränserna i app/validation.py avvisar för långa värden och släpper igenom värden på gränsen
- [ ] Överlåtelse-endpointsen i app/routes/user/ är taktade per användare
- [ ] Proven anropar ROUTEN, inte bara tjänsten under den, så behörighetsspärr och omdirigering täcks

## Implementation hints

- app/deps.py: get_user_or_redirect, get_admin_or_redirect, check_rate_limit
- app/routes/admin/takeovers.py: takeover_action hanterar både länk och samling via fältet kind
- app/config.py: LinkStatus, RATE_LIMIT_PER_HOUR, RATE_LIMIT_PER_HOUR_IP
- app/validation.py: MAX_URL_LENGTH, MAX_TEXT_LENGTH, validate_length
- app/csrf.py: alla POST-formulär kräver csrf_token, validerat mot sessionens hemlighet. Fixturen måste hämta ett giltigt token, annars faller varje POST på 403 och proven mäter fel sak
- app/database.py: init_db() bygger schemat, get_db() är en contextmanager

## Verification

- pytest -q ska gå igenom
- pytest tests/ -k takeover -v visar att både bypass-provet och admin-regressionen körs
- git stash && pytest tests/ -k takeover: bypass-provet ska FALLA mot koden utan fixen. Faller det inte mäter provet fel sak
- ls data/links.db efter en körning: filen får inte ha ändrats

- ID: `01M1XT2QFEJS4PDH92XP8PW1E8`
- Type: chore
- Actor: human:rasmus

---

## [P2][done] [svky] Alla besökare delar rate limit-hink bakom Caddy - kritiskt nu när spärren fungerar

Mätt 2026-08-20 mot lokal instans, uvicorn 0.30.6. ÅTGÄRDAD i commit ef9337a + d444edb, träder i kraft vid nästa docker compose up -d.

PROBLEMET: uvicorns ProxyHeadersMiddleware har trusted_hosts='127.0.0.1' som default (verifierat i installerad källkod, config.py:333 läser FORWARDED_ALLOW_IPS). Caddy når appen från containernätets 172.x-adress, alltså inte 127.0.0.1, så X-Forwarded-For ignorerades och request.client.host blev Caddys adress för samtliga besökare.

Mätt före: två anrop med olika X-Forwarded-For från en klient utanför 127.0.0.1 gav EN distinkt rad i rate_limits. Sex olika personer som begärde inloggningslänk från samma klientadress: den sjätte fick 'För många försök'. Sex olika användare som beställde varsin kortlänk: den sjätte spärrad.

Varför det inte märkts: fram till commit fee21f0 räknade check_rate_limit alltid noll (se TASK-1434), så ingen spärr har haft effekt.

ÅTGÄRDAT PÅ TVÅ SÄTT (Rasmus val 2026-08-20):
1. ef9337a - inloggningsspärren nycklas på e-postadressen i stället för IP. Mätt efter: sex olika personer från samma adress släpps igenom, samma adress sju gånger spärras på det sjätte försöket. Överlåtelseflödena nycklas på user:<id> sedan 3f7d5b2.
2. d444edb - FORWARDED_ALLOW_IPS='*' i docker-compose.yml, så uvicorn litar på Caddys X-Forwarded-For och de fortfarande IP-nycklade flödena (anonym beställning, återutskick, takeover) räknar per besökare. Mätt efter: två X-Forwarded-For ger två distinkta hinkar. Värdet förutsätter att svky-tjänsten inte publicerar någon port utåt - den gör inte det i compose-filen.

KVAR ATT GÖRA I DRIFT: verifiera efter deploy att ip-kolumnen i prods rate_limits innehåller riktiga besökaradresser och inte en enda 172.x-adress.

ÖVRIGT: Caddyfile saknar request_body max_size, så ingen body-gräns finns framför appen. Längdgränserna i 2196a50 sitter i valideringen och täcker fälten.

- ID: `01M0GF47B53YC81762BDPN6F44`
- Type: bug
- Actor: human:rasmus

---

## [P2][done] [svky] Rate limit-räknaren räknade alltid noll - ingen spärr har fungerat

Upptäckt under arbetet med TASK-1425, mätt mot lokal instans 2026-08-20.

check_rate_limit jämförde created_at mot datetime.now(UTC).isoformat() (2026-08-20T19:49:46) medan raden skrivs av CURRENT_TIMESTAMP som '2026-08-20 20:49:27'. SQLite jämför som strängar och mellanslag (0x20) sorterar före T (0x54), så varje rad föll utanför fönstret och COUNT blev alltid 0.

Utfall: ingen av spärrarna har spärrat - login, resend, beställning, takeover och kontoborttagning har alla varit ospärrade sedan de infördes. Granskningen 2026-08-20 antog att rate limiting fungerade och bedömde TASK-1425 som lågallvarlig avvikelse mot ett fungerande mönster.

Mätt före fix: 7 anrop i rad gav 7 genomsläpp. Efter fix (jämförelse i SQL mot datetime('now', '-1 hour')): 5 genomsläpp, 429 på det sjätte.

Fixad i commit fee21f0.

- ID: `01M0GF3F328V60MHD3GPHV7HRD`
- Type: bug
- Actor: human:rasmus

---

## [P2][done] [svky] POST /admin/takeover-action saknar admin-kontroll som GET-varianten har

Behörighetsbypass, BEKRÄFTAD MED MÄTNING mot lokal instans 2026-08-20 (kontrollfall isolerar orsaken).

GET /admin/takeover-action/{token} (takeovers.py:243) anropar get_admin_or_redirect(request) på första raden. POST-varianten (takeovers.py:309, takeover_action) gör INTE det - den validerar bara CSRF och utför sedan ägarbytet via _handle_link/bundle_takeover_action. Enda av ~25 admin-POST-routes som saknar admin-koll.

Roll: någon utan admin-session som fått tag i en giltig takeover-action-token (itsdangerous-signerad, 7 dagars giltighet, mailas till admin - kan läcka via mail-scanner-förhandsvisning, vidarebefordrat mail, mailrelä-logg, referrer).

Repro (mätt): seedade offer + länk 'offermal' (owner_id=1) + pending takeover till angripare. (1) Hämtade anon-CSRF från GET /login utan session. (2) KONTROLL A: GET action-URL utan admin -> 303 till /login (kollen fungerar där). (3) KONTROLL B: POST med fel CSRF -> 403 (CSRF enda grinden). (4) EXPLOIT: POST med anon-CSRF, ingen admin-session -> 303 approved, länkens owner_id ändrades 1->2 (angripare). Efter: takeover_request=approved.

Utfall: icke-admin kan godkänna/avslå en överlåtelse (flytta ägarskap av kortlänk/samling) helt utan inloggning - kringgår den behörighetsgräns koden själv har på GET.

Fix: lägg get_admin_or_redirect(request) först i takeover_action, analogt med GET. Kolla samtidigt bundle-motsvarigheten.

Klart när: POST /admin/takeover-action utan admin-session ger redirect till /login (som GET), och exploit-reprot ovan flyttar INTE längre ägandet. Verifiera: kör om repro-scriptet, KONTROLL A-mönstret ska nu gälla även POST.

- ID: `01M0GCNTYWT0MGV0EDAGF14BH3`
- Type: bug
- Actor: ai:claude-code

---

## [P2][done] [svky] Dev-instansen är publicerad på 0.0.0.0:8000 med inloggning över oskyddad HTTP

Uppmätt utifrån 2026-08-08 från ubuntu-ai, under TASK-1088.

Port 8000 svarar på http://204.168.252.40:8000/ med dev-instansen - /healthz ger ok true, och framsidan skiljer sig från https://svky.se, alltså inte produktionen. /login svarar 200. Ett lösenord som skrivs där går i klartext över internet, utan TLS.

ss -tlnp på servern visar docker-proxy på 0.0.0.0:8000, alltså publicerad på alla gränssnitt.

EN BRANDVÄGGSREGEL LÖSER DET INTE. Docker skriver egna iptables-regler i DOCKER-kedjan, som konsulteras före ufw:s INPUT. En ufw deny 8000 hade sett rätt ut i ufw status och ändå släppt igenom trafiken. Det är den vanligaste fällan på en Docker-värd med ufw, och skälet att kontrollen måste ske i publiceringen.

ATT GÖRA: bind publiceringen till loopback i docker-compose.dev.yml, alltså 127.0.0.1:8000:8000. Ska dev nås från annan maskin är tailnet-adressen rätt väg nu när servern är ansluten: 100.74.163.31:8000:8000.

VERIFIERA UTIFRÅN, inte i konfigfilen: porten ska sluta svara från en maskin utanför tailnetet. En kontroll som bara läser compose-filen bevisar inte att containern startades om.

Kontrollera samma sak för produktionsstacken - 80 och 443 ska vara publicerade, men ingen apps egen port.

- ID: `01KZGT78WXDQED2S3EM99AANNW`
- Type: bug
- Actor: ai:claude-code

---

## [P3][done] [svky] Admins detaljvy visar en Swish-samling som tom - den hämtar bara bundle_items

GET /admin/bundles/<id> för en Swish-samling säger '0 länkar - redigeras av ägaren', även när samlingen har flera Swish-koder. Kontrollerat 2026-09-09 mot en samling med tre koder.

Orsak: routen hämtar bundle_items och bundle_sections men aldrig swish_items. En Swish-samling bär sina poster i den egna tabellen (migration 11), och adminvyn känner inte till den.

Följden är värre än ett tomt antal: en admin som modererar kan inte se VAD samlingen betalar till. Swish-numret, beloppet och låsmasken är just det en admin skulle behöva granska om någon anmäler en kod - och de syns inte alls.

Listan /admin/bundles räknar redan rätt: den fick swish_count 2026-09-09 i commit ae9fd86. Detaljvyn missades i samma omgång.

DET HÄR ÄR FJÄRDE GÅNGEN samma mönster. Swish-samlingen glöms i en vy som byggdes när alla samlingar bar länkar:
1. QR-rutan i ägarvyn (TASK-1719, rättad)
2. Samlingens namn, beskrivning, statistik och avaktivering i ägarvyn (rättad samma dag)
3. Postens nedladdningsformat (rättad samma dag)
4. Den här

Värt att fråga sig om det finns fler. En genomgång av varje ställe som gör SELECT mot bundle_items vore billigare än att hitta dem en i taget.

Klart när: adminvyn visar Swish-samlingens koder med rubrik, mottagare, belopp och vad betalaren får ändra - alltså det en moderator behöver för att bedöma dem.

Verifiera: prov som anropar ROUTEN med en swishsamling och kontrollerar att en kods rubrik och mottagare står i svaret. Provet ska falla mot dagens kod - kör det före fixen och se att det gör det. shot vid 390px och 1280px.

- ID: `01M2366H9XY74Z8X559YD249S6`
- Type: bug
- Actor: ai:claude-code

---

## [P3][done] [svky] Val per swishpost om mottagarnumret ska visas i klartext på samlingssidan

I dag står mottagarnumret bara i ÄGARENS vy. Den publika sidan visar ändamål, belopp, knapp och QR-kod, men aldrig numret som text.

Rasmus vill kunna välja att skriva ut det - per post, och med ett sätt att sätta alla på en gång.

TOLKNING SOM SKA BEKRÄFTAS: att numret visas som läsbar text på den publika samlingssidan, så den som hellre knappar in det själv i Swish-appen kan göra det utan att skanna eller trycka på knappen. Om det i stället handlar om en utskriftsvy - en lapp att skriva ut på papper med koderna och numren - är det en annan och större sak. Fråga innan bygget börjar.

Varför någon vill ha det: en besökare med en telefon som inte kan skanna, eller som fått sidan uppläst, har i dag ingen väg fram om knappen inte fungerar. Numret i klartext är den vägen.

Varför någon INTE vill ha det: ett Swish-nummer i klartext på en publik sida är lättare att samla in maskinellt än ett inbakat i en QR-kod. För ett församlingsnummer spelar det troligen ingen roll, men valet ska vara ägarens och därför per post.

BERÖRS:
- swish_items behöver en kolumn, förslagsvis visa_mottagare med default 0. Migration 12 - 10 är ett hål och 11 är swish_items.
- Kryssruta per post i mina_swishsamlingar_detalj.html, plus en knapp eller kryssruta som sätter alla i samlingen på en gång.
- app/templates/swish_bundle.html visar numret när flaggan är satt.
- lastext i app/swishtext.py nämner redan mottagaren för ägaren - texten på den publika sidan är en annan sak och ska inte återanvända den.

Klart när: ägaren kan slå på numret för en post eller för hela samlingen, och det syns på den publika sidan bara för de poster som har det påslaget.

Verifiera: prov som anropar routen och kontrollerar att numret INTE står i svaret när flaggan är av - ett prov som bara kollar att det står där när den är på missar hela poängen. shot vid 390px och 1280px med blandade lägen i samma samling.

- ID: `01M22SSHPYQKYJ61P52K6FY2S0`
- Type: feature
- Actor: ai:claude-code

---

## [P3][done] [svky] Utred om Swish-länkarna ska gå via ett domännamn i stället för swish://

Vi bygger i dag swish://payment?data=<URL-kodad JSON>. En egen URI-scheme har kända svagheter som ett vanligt https-domännamn inte har - frågan är om Swish erbjuder en sådan väg, och om den beter sig bättre.

VAD SOM TALAR FÖR ATT UTREDA:
- En swish://-länk gör ingenting alls när Swish inte är installerat. Ingen sida, inget besked, ingen hjälp att komma vidare. En https-adress kan åtminstone visa något.
- Flera appar och webbvyer vägrar öppna okända scheman. Länken i ett e-postutskick eller i ett CMS kan alltså vara död utan att avsändaren ser det.
- Formatet är odokumenterat och härlett ur appen, se docs/swish-applankens-format.md. Ett publikt dokumenterat format vore mindre bräckligt.
- Universal Links (iOS) och App Links (Android) öppnar appen direkt från en https-adress och faller tillbaka på webbsidan när appen saknas. Det är mönstret frågan handlar om.

VAD SOM SKA TAS REDA PÅ:
1. Publicerar Swish någon https-form alls, och i så fall var den är dokumenterad? Vår befintliga spec (Guide Swish QR code design specification v1.7.2) täcker QR-strängen, inte länkar.
2. Om den finns: bär den samma fält (mottagare, belopp, meddelande, låsmask) och beter den sig likadant på telefon? Mätning på riktig telefon krävs, som för swish:// - allt vi vet i dag kommer från mätning, inte från dokumentation.
3. Gäller mätning 4 även där, alltså att mottagaren går att ändra så fort något fält är fritt? Antag inte att den inte gör det.

OM SVARET ÄR NEJ är utredningen ändå värd något: skriv ner i docs att vi kollat och varför swish:// står kvar, så nästa person slipper ställa frågan igen.

BERÖRS: app/swish.py (applank), och de fyra ställen som visar länken - swish_generator.html, swish_bundle.html, swishsamlingar.py och public.py. Byts formen ut ska det ske på ETT ställe, i applank(), precis som docstringen där redan säger.

Klart när: docs/swish-applankens-format.md har ett avsnitt som svarar ja eller nej med källa, och vid ja en task för bytet.

- ID: `01M22S2VF7NY0ZNNP149KMD18Y`
- Type: spike
- Actor: ai:claude-code

---

## [P3][done] [svky] Swish-samlingens ägarvy saknar QR-väljaren och zip som andra samlingar har

Gäller samlingens EGEN kortkod, alltså svky.se/dk-swish - inte betalkoderna i posterna.

En vanlig samling har en QR-ruta som fälls ut med en trelägesväxel (ingen sköld, svart sköld, färgsköld) som byter bild utan omladdning, plus tre nedladdningar: SVG för tryck, PNG och Alla varianter (zip). Swish-samlingens ägarvy har bara en naken länk till qr.svg.

Det är ett fel jag införde 2026-09-08 när samlingsvyn delades i två mallar. Ingenting i backend saknas.

KONTROLLERAT 2026-09-09 mot en körande Swish-samling:
- GET /mina-samlingar/1/qr.zip -> 200
- GET /mina-samlingar/1/qr.png?symbol=skold-farg -> 200

Routerna min_samling_qr och min_samling_qr_paket i app/routes/user/bundles.py gäller alla bundles oavsett tema och behöver inte röras.

Det som ska göras: kopiera QR-rutan ur app/templates/mina_samlingar_detalj.html (raderna kring 257-280, klassen .qr-ruta med data-qr-open, data-qr-val och data-qr-lank) in i mina_swishsamlingar_detalj.html, och byt den nakna qr.svg-länken mot knappen som fäller ut den. Stilen .qr-ruta ligger redan i den vanliga mallens extra_style och följer inte med automatiskt.

app/static/qr.js sköter växeln och länkarna - kontrollera att den laddas för den här mallen också.

Klart när: ägaren till en Swish-samling kan välja symbol och ladda ner PNG, SVG eller zip för samlingens kortkod, precis som för en vanlig samling.

Verifiera: klicka växeln och bekräfta att bilden byter utan omladdning OCH att nedladdningslänkarna bär valet - att bilden byter är inte samma sak som att länken gör det. Ladda ner zip och räkna filerna, sex stycken. shot vid 390px och 1280px.

- ID: `01M22RF639603XJ099E71RAMJG`
- Type: feature
- Actor: ai:claude-code

---

## [P3][done] [svky] Tabellen på /admin/links är bredare än containern - åtgärdsknapparna kapas

Kolumnen ÅTGÄRDER hamnar utanför containern och knapparna klipps mitt i. Rasmus skärmdump 2026-09-09 visar det vid full desktopbredd, alltså inte bara ett mobilproblem: Detalj och QR syns, resten av knapparna skärs av vid högerkanten.

Tabellen har nio kolumner (Kod, Mål-URL, Ägare, Status, Klick, Senast använd, Skapad, Åtgärder). Flera av dem bär text som inte kortas: ägarens hela e-postadress bryts på två rader, och SKAPAD bryter datum och tid på var sin rad, medan SENAST ANVÄND får plats på en. Måladressen kortas redan med ellips - det gör inte de andra.

Rasmus vill ha en genomgång av listan från ui/ux-håll, inte bara en overflow-fix. Frågan är vad admin faktiskt behöver se i en lista över 34 kortlänkar, och vad som hör hemma på detaljsidan. Kandidater att väga: slå ihop de två datumkolumnerna, korta ägaren till användarnamnet med hela adressen i title, och göra åtgärderna till en meny i stället för fyra knappar per rad.

Klart när: åtgärdsknapparna går att träffa i sin helhet, och tabellen inte spränger sin container.

Verifiera: shot vid 390px OCH 1280px med en admin-session och minst 20 rader i listan, båda gånger med document.documentElement.scrollWidth lika med viewportbredden. Klicka varje åtgärd i en rad och bekräfta att den gör det den heter - en knapp som renderas är inte en knapp som fungerar. Se browser-verify-skillen.

- ID: `01M22ED8XCQZH2K4SKH0D6ME44`
- Type: bug
- Actor: ai:claude-code

---

## [P3][done] [svky] Bygg Swish-samlingen: flera betalkoder på en sida med en kortkod

Den starkaste delen av Rasmus ursprungliga idé, och den enda som inte är byggd.

En lapp i domkyrkan bär i dag tre Swish-koder: diakoni, musikverksamheten och dagens kollektändamål. Tre koder på en lapp är svåra att träffa rätt på, och kollektändamålet byts varje vecka medan lappen sitter kvar. En kod som leder till en sida med alla tre löser båda.

Beslut som redan är fattade, se kommentarerna på TASK-1673:

Egen tabell för swishposter, inte bundle_items. Den bär title och url, alltså länkar. En swishpost behöver mottagare, belopp, meddelande och låsmask, och har varken sektioner, ikon per post eller externa länkar.

Enhetsdetektering görs INTE på servern. User-agent är opålitligt och tjänsten sparar medvetet inget om besökaren. Använd @media (pointer: coarse) eller en breddkontroll i JS, med en synlig växel 'Jag ska skanna i stället'. Visa aldrig bara det ena: på mobil knappen stor och koden under, på dator tvärtom.

Statistik per ändamål faller ut gratis och är värd att ta med. Vilket kollektändamål trycker folk på är något en papperslapp aldrig kunde svara på.

Grunden finns: app/swish.py bär QR-strängen och applänken, båda mätta mot en riktig telefon 2026-09-08. app/routes/swishgenerator.py visar mönstret för hur en betalning renderas.

VARNING som måste in i gränssnittet: en applänk med fritt belopp låter den som öppnar den peka om betalningen till ett annat nummer. Mottagaren går inte att låsa när något fält är fritt. Se docs/swish-app-link-format.md, mätning 4. Generatorn varnar redan, samlingen måste göra det också.

Verifiera: prov som anropar ROUTEN, avkodning med zxing som resten av QR-proven, och shot vid 390px OCH 1280px av samlingssidan i båda lägena.

- ID: `01M213WKW1PHWCFCPFC1DX5FW2`
- Type: feature
- Actor: ai:claude-code

---

## [P3][done] [svky] Designspecifikation som avgör komponentval i gränssnittet

Genomgång av hela gränssnittet, och en spec som AVGÖR val i stället för att beskriva nuläget.

Rasmus exempel: raden 'Ansök om rätt att länka externt' på /mina-lankar är i dag en textlänk i en informationsruta. Ska den vara det, eller en knapp? Specen ska svara, och bära regeln som gör att nästa person kommer till samma svar utan att fråga.

Mätt 2026-09-08: btn-secondary btn-sm används 82 gånger, btn-primary 27, utan att något skrivet säger varför. 93 respektive 74 inline style-attribut i mina_samlingar_detalj.html och my_links.html. Tjugo mallar har egna extra_style-block vid sidan av style.css på 405 rader.

Resultatet ligger i docs/design.md.

- ID: `01M210D693YXA9EWE9B4QXSW0G`
- Type: task
- Actor: ai:claude-code

---

## [P3][done] [svky] Ge samlingar QR-koder, och visa QR i admin-gränssnittet

## Context

Samlingar saknar QR-koder helt, och admin kan inte se någon QR i gränssnittet.
Tabellen `bundles` har en unik `code` precis som `links`, och en samling delas
på samma sätt. En samling är dessutom det som oftast trycks på ett anslag,
eftersom den bär flera länkar bakom en adress.

Admin har redan routen `/admin/links/<id>/qr.<andelse>` med symbolval - den
delar `_qr_svar` med användarens. Det som saknas är rutan i mallen.

Hela mekaniken finns byggd sedan 2026-09-08 och ska återanvändas, inte
kopieras.

## Acceptance criteria

- [ ] `GET /mina-samlingar/<id>/qr.png` och `qr.svg` ritar samlingens kod, med
      `?symbol=skold-svart` och `?symbol=skold-farg` som för länkar
- [ ] `GET /mina-samlingar/<id>/qr.zip` ger sex filer med sex olika namn
- [ ] En annan användares samling ger 404, utloggad ger 303 till `/login`
- [ ] Samlingsvyn (`mina_samlingar_detalj.html`) har samma QR-ruta som
      `my_links.html`: trelägesväxel, bild som byts utan omladdning, och
      nedladdningslänkar som bär det valda läget
- [ ] Admin har QR-rutan i `admin/links.html` med samma växel
- [ ] Admin når `qr.zip` för en länk, vilket i dag bara finns under
      `/mina-lankar`
- [ ] Admin kan se QR för en samling
- [ ] Alla nya svar bär ETag och `Cache-Control: private, no-cache`, som de
      befintliga

## Implementation hints

Ritningen är klar och rörs inte: `app/qr.py` bär `png()`, `svg()`, `SYMBOLER`,
`valj_symbol()` och `filnamn()`.

Svarshanteringen ligger i `app/routes/user/links.py`:

- `_bildsvar(kropp, typ, filnamn, request)` - ETag och 304, återanvänd rakt av
- `_qr_svar(link_id, andelse, agare, symbol, request)` - slår i `links`
- `_qr_paket(link_id, agare, request)` - bygger zipen i minnet

De två sista slår hårdkodat mot `links`. Välj EN väg: en tabellparameter, eller
syskonfunktioner för `bundles`. Duplicera inte zip-bygget - filnamnen måste
förbli unika, och det kravet finns redan mätt i `tests/test_qr.py`.

Ordningen på routerna spelar roll: `qr.zip` måste stå FÖRE `qr.{andelse}`,
annars fångar den senare `zip` som en ändelse och svarar 404. Se kommentaren
vid `my_link_qr_paket`.

Växelns JavaScript ligger i `{% block scripts %}` i `my_links.html` och lyssnar
på `[data-qr-val]`. Det är generiskt och bör flyttas till en delad plats i
stället för att kopieras in i två mallar till.

Frågan om `RESERVED_CODES` är redan besvarad: samlingskoder valideras, se
kommentaren på tasken. Rör inte den delen, men överväg att samla de tre
kontrollerna i `validate_code` om du ändå är inne i `bundles.py`.

## Verification

- `pytest tests/test_qr.py -q` - alla befintliga prov ska stå kvar gröna
- Nya prov ska anropa ROUTEN, inte tjänsten under den, och avkoda med
  `_zxing()` som resten av QR-proven. Minst: ägare får sin kod, annan
  användare får 404, utloggad får 303, admin når båda, zipen bär sex unika
  namn
- `pytest -q` - hela sviten
- `ruff check app/` och `ruff format --check app/` - CI kör bara `app/`
- Browser: starta appen (`svc port` för ledig port), klicka QR-knappen i
  samlingsvyn och i admin, och växla mellan alla tre lägena. Bekräfta att
  bilden OCH båda nedladdningslänkarna byter variant - en växel som bara
  uppdaterar förhandsvisningen är det troliga halvfelet
- `shot <url> ut.png --width 390` och `--width 1280` för samlingsvyn och
  adminvyn. Ingen horisontell overflow, och QR-rutan ska rymmas i kortet

- ID: `01M20QAAWMEKVC2B4Z4Y5QZVYY`
- Type: feature
- Actor: ai:claude-code

---

## [P3][done] [svky] Val att lägga Svenska kyrkans sköld i mitten av QR-koden

En växel på QR-kod-vyn som lägger skölden i mitten av koden, utan omladdning av sidan. Samma mekanik som Swish-symbolen ska få (TASK-1673), och samma ritväg.

Förebilden finns färdig i slöjda.de: app/services/qrkod.py. Läs den innan du börjar - den bär tre saker som kostat tid att komma fram till:

1. Varje symbol har EGNA regler i en Symbolinstallning-dataklass: sökväg, andel av kodens bredd, och om en vit kontrastplatta ska läggas bakom. Hemslöjdens H får platta (24 procent), Swish får INTE det (25 procent) eftersom Swish egna riktlinjer kräver att filens egen runda vita bakgrund står orörd. Skölden och Swish delar alltså inte behandling.
2. Nedskalning måste ske så att kanterna inte smutsas ner. Symbolfilerna bär svart i färgkanalerna där de är genomskinliga, och LANCZOS blandar in svärtan i kantpixlarna - resultatet blir en mörk frans mot den vita plattan.
3. Symbolen kräver felkorrigering H. Kortlänkar kör M sedan 2026-09-07 (FELKORRIGERING_LANK i app/qr.py), så en kod MED sköld måste ritas om med FELKORRIGERING_SWISH - inte bara få en bild pålagd.

Växeln ska vara async: byt bilden utan att ladda om sidan, och behåll valet i nedladdningslänkarna för PNG och SVG.

Verifiera: att koden fortfarande går att avkoda MED symbolen (tests/test_qr.py avkodar redan med cv2 - lägg ett fall för sköldvarianten), shot vid 390px OCH 1280px, och att klicket på växeln faktiskt byter bild.

- ID: `01M209F7EVQGGB856QYBZ9KV4X`
- Type: feature
- Actor: ai:claude-code

---

## [P3][done] [svky] Låt användare ansöka om rätt att länka utanför de tillåtna domänerna

## Context

Rätten att peka en kortlänk utanför `allowed_domains` styrs i dag av två
flaggor på användaren, `allow_any_domain` och `allow_external_urls`. Bara
admin kan sätta dem, och det finns ingen väg att be om dem. En användare som
behöver rätten vet inte ens att den finns, så frågan når aldrig admin.

Överlåtelseflödet är förebilden och ska härmas, inte uppfinnas om: tabellen
`transfer_requests`, vyn `/admin/takeover-requests`, badgen i adminbaren
(`pending_takeover_count` i `app/routes/admin/helpers.py`) och det
skanner-säkra e-postmönstret.

## Acceptance criteria

- [ ] En inloggad användare kan ansöka från `/mina-lankar` med en motivering
      i fritext. Motiveringen är obligatorisk - admin behöver veta varför
- [ ] Ansökan går inte att skicka två gånger medan en väntar
- [ ] `/mina-lankar` upplyser om att möjligheten finns, även för den som
      aldrig ansökt
- [ ] Admin ser väntande ansökningar i en egen vy med motiveringen synlig,
      och en badge i adminbaren som räknar dem
- [ ] Admin kan godkänna eller avslå. Ett godkännande sätter flaggan på
      användaren, ett avslag gör det inte
- [ ] Användaren får e-post vid både godkännande och avslag
- [ ] Alla POST-formulär bär `csrf_token` och avvisar en ogiltig med 403
- [ ] En vanlig användare når inte adminvyn (303 till `/login`), och kan inte
      godkänna sin egen ansökan

## Implementation hints

Flaggorna och deras uppslag ligger i `app/deps.py`: `user_allows_any_domain()`
och `user_allows_external_urls()`. Rör inte deras signatur - `app/validation.py`
och beställningsflödet anropar dem.

Ny tabell i `app/database.py`, efter mönstret för `transfer_requests` (raderna
kring 113). Migrationer sker med `ALTER TABLE`-guards i `init_db()`, inte med
Alembic. Fälten som behövs: användare, vilken rätt som söks, motivering,
status, tidsstämplar.

Admin-routen hör hemma i en ny fil i `app/routes/admin/`, inkluderad från
`app/routes/admin/__init__.py`. Se hur `takeovers.py` gör.

Badgen: `pending_takeover_count()` i `app/routes/admin/helpers.py` visar
mönstret, och `app/templates/admin/_bar.html` visar hur den renderas.

E-post: lägg funktionerna i `app/mail.py` bredvid de befintliga elva. De bygger
HTML inline och skickar via SMTP.

Ändrar du en e-postlänk som ändrar tillstånd gäller det skanner-säkra mönstret
utan undantag: GET renderar BARA en bekräftelsesida, POST med CSRF utför
åtgärden. Microsoft Safe Links hämtar annars länken och bränner den. Se
`/verify/<token>` i `app/routes/public.py` för ett färdigt exempel.

## Verification

- `pytest tests/ -q -k "ansok or behorighet"` för de nya proven, och
  `pytest -q` för hela sviten när du är klar
- Proven ska anropa ROUTEN, inte tjänsten under den. Minst: utloggad får 303,
  vanlig användare når inte adminvyn, POST utan giltigt `csrf_token` ger 403
  och sparar ingenting, dubbel ansökan avvisas, godkännande sätter flaggan,
  avslag sätter den inte
- `ruff check app/` och `ruff format --check app/` - CI kör bara `app/`
- Browser: starta appen (`svc port` för ledig port), fyll i formuläret som
  vanlig användare, godkänn som admin, och bekräfta att flaggan slår igenom
  genom att beställa en länk mot en domän som inte står i `allowed_domains`
- `shot <url> ut.png --width 390` och `--width 1280` för ansökningsformuläret
  och adminvyn. Ingen horisontell overflow

- ID: `01M202M9R1851MKNJS1CJ3YF6W`
- Type: feature
- Actor: ai:claude-code

---

## [P3][todo] [svky] Byt ut marked-förhandsvisningen mot EasyMDE i alla markdown-redigerare

Fyra redigerare skriver markdown i dag, alla med samma lösning: en textarea plus live-förhandsvisning via marked. Ingen av dem har EasyMDE.

Att byta:
- admin/notis_edit.html (notisbannern)
- admin/om_edit.html (delas av Om-sidan, Integritet och Nyheter)
- admin/snabblänkar.html (introtexten på startsidan)
- mina_samlingar_detalj.html (samlingens brödtext, användarsida - inte admin)

EasyMDE ska köras UTAN fullskärmsvyn. Toolbaren behöver anpassas per plats: notisbannern är en till tre rader och ska inte få samma verktygsrad som en hel om-sida.

Markdown renderas på fem ställen i appen (render_markdown i public.py och templating.py): om, integritet, nyheter, samlingens brödtext och startsidans introtext. Alla fem har alltså en redigerare - inget ställe saknar redigerare helt.

Verifiera: shot vid 390px OCH 1280px per redigerare, och att SPARA fungerar från EasyMDE-instansen (den ersätter textarean med en CodeMirror-yta, och ett formulär som postar tom text är det tysta felet här). Kolla också ljust och mörkt läge - EasyMDE:s toolbar-ikoner ärver textfärg och har försvunnit mot ljus bakgrund i andra projekt.

- ID: `01M1ZVY10JK2SV21GYE59GW98Z`
- Type: improvement
- Actor: ai:claude-code

---

## [P3][done] [svky] Driftytan ska visa när driftkoden ligger efter, och kunna hämta den

## Context

Appens kod når servern genom en signerad image. Driftkoden - drift/*.sh, drift/*.py och systemd-enheterna - når den bara genom att någon kör git pull, sudo install och sudo cp för hand.

Mätt 2026-09-07, samma kväll som knapparna byggdes: de fyra begaran-enheterna i /etc/systemd/system/ skilde sig från utcheckningen. Fixen StartLimitIntervalSec=0 hade aldrig kopierats dit. reset-failed och restart tog bort varningen från sidan, så det SÅG lagat ut medan startgränsen satt kvar och knapparna kunde dö tyst igen.

Det är samma mönster som CI-raden: utan något som säger att koden ligger efter läses tystnad som framgång.

Slöjda löste det med två knappar och en timer, se docs/ci-cd.md i ~/workspace/hemslojden/anmälningssystem, avsnitten om att driftkoden når servern genom en knapp och om att utrullningen är en andra knapp.

## Två frågor, som slocknar vid olika tillfällen

1. **Ligger utcheckningen efter origin/main?** Slocknar när koden hämtats.
2. **Skiljer sig de rotägda kopiorna från utcheckningen?** Slocknar först när de rullats ut.

Slöjda skiljer på dem med flit (drift_andrat och drift_ej_utrullat). Att slå ihop dem döljer att en hämtning lyckades men utrullningen inte gjordes.

## Ordning

Ta VISA-halvan först. Den är riskfri och tar bort själva faran: att köra gammal driftkod utan att veta om det. Knapparna är en bekvämlighet ovanpå.

## Acceptance criteria

VISA:
- [ ] Samlaren jämför HEAD mot origin/main och rapporterar hur många commitar efter, plus målcommitens ämnesrad så man vet vad som hämtas
- [ ] Samlaren jämför varje rotägd kopia (/usr/local/bin/svky-driftyta och enheterna i /etc/systemd/system/) mot utcheckningen och listar de som skiljer sig
- [ ] Ytan visar båda, som SKILDA rader
- [ ] Läget degraderas till okänt när git fetch misslyckas - en frusen fil som säger i fas är värre än ingen

HÄMTA (senare):
- [ ] Knapp som gör git fetch och merge --ff-only. ALDRIG reset --hard: finns lokala commitar på servern ska kommandot vägra, inte kasta dem tyst
- [ ] Egen knapp för utrullningen av de rotägda kopiorna. Slöjdas skäl: hämtningens enhet är härdad och kan inte skriva i /usr/local/bin och /etc, och bara ETT jobb åt gången kan vara aktivt - kedjade jobb var aldrig ett alternativ
- [ ] En fallerad utrullning får inte dölja att koden hämtades

## Verification

- Backa utcheckningen en commit och bekräfta att ytan säger att den ligger efter
- Ändra en enhetsfil i utcheckningen utan att kopiera den, och bekräfta att ytan säger att den inte är utrullad
- Bryt nätet mot GitHub och bekräfta att raden säger okänt, inte i fas

## Varför en knapp och inte automatik

Imagen är signerad och servern verifierar den. En git-utcheckning har ingen motsvarande grind. Läte man GitHub utlösa en pull hade kan pusha till main blivit samma sak som kan köra kod som root på värden - en STÖRRE rättighet än dagens deploy. En timer valdes bort av samma skäl: koden ska inte bytas utan att någon tittar.

- ID: `01M1YPK4MVSBQR7MEHEB3H77DA`
- Type: feature
- Actor: human:rasmus

---

## [P3][done] [svky] Driftyta för svky.se, tailnet-only och utan argument

## Context

Allt maskineri finns redan som jobb och skript: svky-uppdatera-staging.sh, svky-promotera.sh, svky-verifiera.sh, svky-digest.sh. Det som saknas är en yta att se läget på och trycka på knappar från, utan ssh.

TASK-1689 (knappen som kollar efter ny version direkt) beror på den här.

## Formen är viktigare än funktionen

**Får INTE ligga i svky-appens adminyta.** Kan appen starta jobb på värden blir ett appintrång detsamma som root. Egen tjänst, egen systemd-enhet, egen användare.

**Nås bara över tailnet**, som Mailpit och staging. Ingen publik DNS-post, ingen ACME. tailscale serve på egen port.

**Inga argument från webben.** Varje operation är ett verb utan parametrar - ytan kan inte peka ut en digest, en container eller ett kommando. Vad operationen gör står i koden. Då räcker sudoers-rader utan wildcard:

    svky-ops ALL=(root) NOPASSWD: /usr/bin/systemctl start svky-staging-uppdatera.service

Slöjdas kontrollplan har socket, broker med egen identitet, path-enhet och globalt lås. Det behövs INTE här: svky har två operationer, inte fyra, och ingen PostgreSQL eller backup att samordna. Bygg inte den apparaten.

## Vad ytan ska VISA

Läget, som är den halva man använder oftast:

- Vilken digest och commit staging respektive produktionen kör, och om de skiljer sig
- Vad :latest pekar på just nu, och om det är nyare än staging
- Senaste körningen av svky-staging-uppdatera.service: när, utfall, och orsak vid fel
- Senaste CI-körningen på main. Utan den raden vet ytan bara vad som NÅTT servern, och ett bygge som faller når den aldrig - tystnad läses som framgång. Kräver en fine-grained token med ENDAST Actions: read
- Uppetidssondens läge

## Vad ytan ska KUNNA

Två knappar, båda utan argument:

- Kolla efter ny version nu (TASK-1689) - startar svky-staging-uppdatera.service
- Promotera staging till produktion - startar svky-promotera.sh --ja

Promotionsknappen kräver en uttrycklig bekräftelse i ytan, inte bara ett klick. Den byter version i drift.

## Acceptance criteria

- [ ] Egen tjänst, inte i svky-appen, nåbar bara över tailnet
- [ ] Visar allt under VISA ovan, och säger uttryckligen när en uppgift inte gick att hämta - en panel som ser tom ut när nätet är nere säger samma sak som ingenting har hänt, och det är fel svar på rätt fråga
- [ ] Två knappar, inga parametrar, sudoers utan wildcard
- [ ] Ett jobb åt gången: trycks en knapp medan ett jobb kör ska ytan säga det, inte köa. Skripten har redan flock
- [ ] Läget degraderas till okänt när underlaget är gammalt. En frusen fil som säger allt är bra är värre än ingen fil alls

## Verification

- Nå ytan från en annan tailnet-enhet, och bekräfta att den INTE svarar på serverns publika adress
- Tryck varje knapp och följ jobbet i journalen
- Försök starta något annat genom samma sudo-väg och bekräfta att den nekar
- Stäng av nätet mot GitHub och bekräfta att CI-raden säger att den inte kunde hämtas, inte att allt är bra
- Framkalla ett fel i promoteringen och bekräfta att ytan visar orsaken, inte bara misslyckades

- ID: `01M1YGZ19Z4A207D99WAEY9PT4`
- Type: feature
- Actor: human:rasmus

---

## [P3][todo] [svky] Sammanför dev-compose: main publicerar 8000 brett, dev-branchen gör det inte

## Context

docker-compose.dev.yml på main har ports: "8000:8000", som binder alla gränssnitt. Branchen dev har i stället den säkra bindningen till 127.0.0.1. Fixen finns alltså, men bara på dev, och TASK-1089 markerades som klar utifrån den.

Den som checkar ut main och kör dev-stacken på en publik maskin exponerar den mot internet, och skyddas bara av molnbrandväggen.

## Acceptance criteria

- [ ] docker-compose.dev.yml på main binder till 127.0.0.1
- [ ] Kontrollerat att dev och main inte skiljer sig i fler filer än avsett

## Verification

- git diff main dev -- docker-compose.dev.yml ska vara tom efteråt
- Efter start: ss -tlnp | grep 8000 ska visa 127.0.0.1, inte 0.0.0.0

- ID: `01M1XWGZQ3A5HG0TK51383TB6K`
- Type: bug
- Actor: human:rasmus

---

## [P3][done] [svky] Besluta hur Swish-länkar räknas i statistiken

Blockerar TASK-1673. En Swish-länk har ingen redirect, så dagens klickmodell går inte att applicera rakt av.

I dag betyder en rad i clicks: någon har hämtat GET /<kod> och fått 302 till målet. Ett klick är alltså ett besök på målsidan. En Swish-länk renderar i stället en sida och stannar där, så det finns inget som motsvarar den händelsen.

Tre vägar:
1. Räkna sidvisningen som ett klick. Siffrorna blir jämförbara i samma lista, men de mäter något annat och blir uppblåsta: ett skannat anslag på en vägg ger en visning utan avsikt att betala, och e-postskannrar hämtar sidan.
2. Räkna bara tryck på Öppna Swish, via en egen route som loggar och sedan skickar vidare till swish://. Mäter avsikt, men missar alla som skannar QR-koden på ett anslag - de trycker aldrig på knappen och är troligen majoriteten.
3. Logga sidvisningen i page_views (tabellen finns och används redan för icke-redirect-sidor) och trycket på knappen som ett klick. Två siffror som betyder olika saker, och statistikvyn får visa båda.

Förordas: alternativ 3. Det behåller betydelsen av clicks och ljuger inte i listan över vanliga länkar.

Klart när / Verifiera:
- Beslutet skrivet i docen och i backlog memory.
- Statistikvyn visar Swish-länkar utan att en läsare tror att en visning är en betalning.

- ID: `01M1XK8EVWKDVGPJ98ZC8X32RJ`
- Type: spike
- Actor: human:rasmus

---

## [P3][done] [svky] Swish-betallänkar: swish://-applänk, QR-kod och landningssida

Ny länktyp i kortlänksgeneratorn: Swish-betalning. Kortkoden leder till en landningssida som öppnar Swish-appen förifylld på mobil och visar QR-koden på desktop. Applänk och QR-kod ligger i samma vy, så användaren kan lägga ut båda.

LÄS docs/swish-qr.md FÖRST. Den är den kanoniska specen och rättar två fel i det ursprungliga underlaget.

Bygg som en avskalad kopia av slöjda.de, inte från grunden: ~/workspace/hemslojden/anmälningssystem/app/services/swish.py och qrkod.py. Den koden är i drift och verifierad mot Rasmus egen prototyp. Kopiera särskilt _skala och _komponera i qrkod.py - de löser en mörk frans runt symbolen som uppstår vid rak LANCZOS-skalning av en PNG med svart i de genomskinliga pixlarna.

I korthet:
- Innehåll: C<payee>;<amount>;<message>;<lock_mask>. Belopp med två decimaler och komma (100,00). Meddelande URL-kodat. lock_mask = payee*1 + amount*2 + message*4, bit satt betyder redigerbar.
- Applänk: swish://payment?data=<URL-kodad JSON>, version "1.0" som sträng, amount.value som sträng i hela kronor. editable sätts bara som true, aldrig false.
- Ritning: qrcode[pil]==8.2, felkorrigering H, Swish-symbolen på exakt 25 % av bredden, ingen egen vit platta bakom den.
- Designen i PDF:ens avsnitt 5 (prickmönster, gradient, avkapat hörn) är utgången. Vanlig svartvit kod med rund symbol i mitten.

Skillnad mot slöjda: där är låsmasken alltid 7. Här väljer beställaren per fält, så masken räknas fram ur tre kryssrutor och applänkens editable-nycklar måste följa samma val.

Ingen koppling till Swish Handel-API, inga certifikat, inga betalningar följs upp. Inget anrop till mpc.getswish.net.

Klart när / Verifiera:
- Enhetstest: kodningen ger exakt specens exempelsträng C1237856901;100,00;12229445;0.
- Avkoda de genererade koderna programmatiskt och bekräfta att strängen kommer tillbaka oförändrad, med symbol i mitten.
- Skanna en kod med Swish-appen på riktig telefon: rätt belopp, rätt meddelande, rätt fält låsta.
- Tryck Öppna Swish på samma kortkod i telefonen, samma resultat via applänken.
- Ogiltigt Swish-nummer och meddelande med otillåtna tecken avvisas i backend, inte bara i formuläret.

- ID: `01M1XK0D2F20FTZRP98NMHFQMR`
- Type: feature
- Actor: human:rasmus

---

## [P3][todo] [svky] QR-kod för varje kortlänk, nedladdningsbar från Mina länkar

Varje kortlänk ska kunna visa och ladda ner en QR-kod direkt i verktyget, så att en användare kan sätta både QR-kod och klickbar länk på en hemsida eller ett anslag.

Omfattning:
- QR-kod genereras lokalt med qrcode[pil]==8.2, felkorrigering H. Samma ritfunktion som Swish-koden i TASK-1673 använder, fast utan symbol i mitten. Se docs/swish-qr.md och slöjda.de:s app/services/qrkod.py.
- Visas i Mina länkar per länk, och i admins länkvy.
- Nedladdning som SVG och PNG. Marginal 4 moduler för tryck.
- QR-koden kodar den publika kortlänken (BASE_URL + kod), inte target_url. Byter länken mål fortsätter QR-koden fungera.

Tas före TASK-1673: den bygger ritvägen som Swish-tasken sedan återanvänder, och är oberoende av statistikbeslutet i TASK-1676.

Klart när / Verifiera:
- Skapa en länk, öppna Mina länkar, ladda ner SVG och PNG.
- Avkoda PNG programmatiskt och bekräfta att strängen är rätt.
- Skanna med en telefon och bekräfta att den landar på rätt målsida.
- Kontrollera i webbläsare vid både 390 px och 1280 px att QR-vyn inte spräcker layouten.

- ID: `01M1XK0D28XEREEWAQ573EN31A`
- Type: feature
- Actor: human:rasmus

---

## [P3][done] [svky] Inga längdgränser på target_url, note, reason, samlingsnamn/beskrivning (DoS/svällning)

Saknad gräns, kodläst + grep-verifierad 2026-08-20. Body-size = verifieringsfråga (Caddy).

Bara 'code' längdvalideras (validation.py:69, 2-60). validate_target_url (validation.py:22-64) och validate_email (validation.py:8) saknar len()-kontroll. Fält target_url, note, reason, bundle name/description, sektionsnamn m.fl. lagras oavkortat i SQLite TEXT. Ingen body-size-middleware i main.py (den enda middlewaren, rad 63, räknar bara sidvisningar).

Roll: inloggad användare (roll 2). Anon /bestall är rate-limitad 5/h, men inloggad har ingen gräns på /mina-samlingar-skapande - stora textfält kan mätta db och tunga sidrenderingar (fälten renderas upprepat på startsida/listor).

VERIFIERINGSFRÅGA: Caddy i prod kan ha request_body max_size som mildrar. Går inte att avgöra ur repot - läs prod-Caddyfile.

Klart när: en rimlig maxlängd (t.ex. target_url 2048, fritext några kB) valideras vid indata och avvisas med tydligt fel. Verifiera: POST med överlångt fält ger valideringsfel, inte lagring.

- ID: `01M0GCPJP2TK0MAN08QPTFYGWX`
- Type: improvement
- Actor: ai:claude-code

---

## [P3][done] [svky] Anslut svky.se-servern till tailnetet, som slojda-server

Rasmus 2026-08-08, uppkommet ur hemslojd TASK-833: när uppetidssonden ändå ska in på servern är det lika bra att servern blir nåbar över tailnet först.

FÖRLAGAN är slojda-server, se docs/ci-cd.md i ~/workspace/hemslojden/anmälningssystem:
- Taggad nod, tag:slojda-server. Taggen är inte kosmetika - taggade noder har ingen nyckelutgång, medan en användarägd nod tyst faller ur tailnetet efter ett halvår.
- Vanlig OpenSSH över tailnet, inte Tailscale SSH.
- Publik port 22 stängd EFTER att SSH över tailnet verifierats.
- Hetzner-brandväggen exponerar bara 80 och 443.
- Rootinloggning avstängd, administratören har sudo med interaktivt lösenord.

ATT GÖRA:
1. Lägg till tag:svky-server i tailnetets ACL med en ägare, annars går taggen inte att använda i en auth key.
2. Skapa en engångs-auth key, förautentiserad och taggad. Inte ephemeral - servern ska stå kvar.
3. Installera tailscale på servern och anslut med hostname svky-server.
4. Verifiera SSH över tailnet från ubuntu-ai INNAN något stängs.
5. Först därefter: stäng publik port 22 i Hetzner-brandväggen.

KLART NÄR: svky-server syns i tailscale status utan nyckelutgång, SSH fungerar över tailnet, och publik 22 är stängd.

BLOCKERAR: TASK-1086, uppetidssonden på den servern.

- ID: `01KZGSQHA2VVA4JQP3YA4HWP14`
- Type: chore
- Actor: ai:claude-code

---

## [P3][done] [svky] Staging och produktion som på slöjda.de, i stället för manuell git pull

Rasmus 2026-08-08. I dag driftsätts svky.se för hand: git pull och docker compose up -d direkt på servern. Det fungerar, men det finns ingen miljö att prova en ändring i innan den möter användarna, och ingen grind mellan att något byggts och att det körs skarpt.

Förlagan finns i anmälningssystemet, se docs/ci-cd.md och docs/miljoer.md i ~/workspace/hemslojden/anmälningssystem. Delarna där:

- Två Compose-stackar med skilda nät, volymer, databaser och hemligheter. Staging på egna namn (dev.<domän>) bakom samma Caddy.
- Push till main bygger, signerar imagen med cosign och driftsätter STAGING automatiskt. Produktionen står stilla.
- Produktionen får nya versioner bara genom promotion från en driftyta, med exakt signerad digest - servern verifierar signaturen själv före deploy.
- Deployvägen är ett forced command med tre validerade argument, så att kunna pusha till main inte är samma sak som att kunna köra kod på värden.
- Hemligheterna ligger utanför git-utcheckningen.

ATT AVGÖRA FÖRST: hur mycket av det som är motiverat här. svky.se är en kortlänkstjänst med mindre rörliga delar än anmälningssystemet, och hela driftytan med promotion-worker kan vara mer maskineri än tjänsten bär. Ett rimligt minimum vore staging plus signerad image och en manuell promotion, utan egen webbyta.

Notera att ett byte av driftsätt rör backupen och återläsningsrutinen också.

- ID: `01KZGSGBYM8RJ6NCKG5C1V3F6C`
- Type: feature
- Actor: ai:claude-code

---

## [P3][todo] [svky] SMTP-fel blockerar inloggning org-brett utan larm

app/mail.py:28-35 loggar och kastar MailError. Anropsställena (app/routes/auth.py:78-80, orders.py:88-90 och 372-374, transfers.py x4, takeovers.py x2) fångar och sätter mail_ok=False eller log.exception. Ingen larmar utåt.

Appbeteendet är korrekt - utskicksstatus ska inte läcka till klienten - men ett SMTP-avbrott (Lettermint nere, fel credentials) blockerar tyst all magic-link-inloggning och all länkverifiering för hela organisationen tills någon hör av sig.

Åtgärd: räkna misslyckade utskick och notifiera vid t.ex. över 5 fel per timme. Rate-limitera till en notis per timme enligt policyns avsnitt 6, annars skickar ett längre avbrott en notis per inloggningsförsök.

Samma mönster finns i kortspelshornan (chicago), troligen samma författarhand.

- ID: `01KYWKZPWDMY0EC4K8R5WYRYNP`
- Type: improvement
- Actor: ai:claude-opus-5

---

## [P3][todo] [svky] Larm när backupen på Hetzner slutar köra (backupen verifierad frisk)

README.MD:101 rekommenderar regelbunden backup ("e.g. daily cp") men det finns inget backupskript i repot, och det går inte att se utifrån om ett cron-jobb faktiskt kör på Hetzner-servern.

Detta är den enda punkten i hela ntfy-genomgången (2026-07-31) som rör förlust av produktionsdata. svky.se är i skarp drift och varje publicerad kortlänk i organisationen beror på databasen.

Kör `crontab -l` (och `systemctl list-timers`) på Hetzner-burken och avgör.
- Kör backupen: lägg en heartbeat på den. Hör ihop med TASK-658 (fas F i ntfy-retrofitten på projektet infra).
- Kör den inte: det är ett större problem än något annat som kom ut av genomgången, och behöver åtgärdas före allt notifieringsarbete.

- ID: `01KYWKZPQVRE56CQWC0Y8T251R`
- Type: chore
- Actor: ai:claude-opus-5

---

## [P4][todo] [svky] Designspecens fyndlista och de fyra oprövade avsnitten

TASK-1708 stängdes 2026-09-09 med sex av tio avsnitt mätta och rättade. Det som lämnades kvar står bara i en kommentar på en STÄNGD task, alltså svårt att hitta. Den här tasken bär det vidare.

OPRÖVADE AVSNITT: 2 (alert vs löptext), 5 (rubriker och knapptexter) och 7 (tomma tillstånd). De handlar om ton och komponentval och går inte att mäta som de övriga. De vilar på läsning och kan bara granskas med omdöme.

FYNDLISTAN, nio punkter längst ner i docs/design.md, oåtgärdad som avsett:
1. Inline style-attribut: 101 i mina_samlingar_detalj.html, 73 i my_links.html. De flesta upprepar deklarationer som redan finns som klasser.
2. 33 mallar har eget extra_style-block. Flera duplicerar samma regler mellan filer - h1-stilen upprepas i minst sex adminmallar trots att .page-title h1 finns.
3. .link-card duplicerar .card fält för fält i stället för att komponera på den.
4. Två bekräftelsemönster lever parallellt. Efter 2026-09-09 är det 21 confirm() i 8 mallar mot 2 mallar med panel - regeln säger att panelen är standarden.
5. Tomma bekräftelsetexter utan konsekvens i admin/bundle_detail.html och admin/snabblänkar.html.
6. hjalpruta i admin/om_edit.html är en egen komponent förklädd till alert-info.
7. Asterisken för obligatoriska fält sätts med inline style color:red i stället för en klass.
8. Testdata-bugg, inte kod: kortlänkarna kollekt och gava i testdatabasen pekar på sig själva.
9. CLAUDE.md:s filstruktur stämmer inte längre med repot - app/routes/user.py och public.py är uppdelade sedan länge.

Punkt 9 är den billigaste och den som förvillar mest, eftersom CLAUDE.md läses först av varje ny session.

Ta dem inte som en klump. Varje punkt är en egen liten städning, och flera rör filer som redan är över tusen rader.

Klart när: punkterna är antingen åtgärdade eller uttryckligen avskrivna med skäl i docs/design.md.

- ID: `01M238H3R6VCJ45XV8JGQ9QXJ4`
- Type: improvement
- Actor: ai:claude-code

---

## [P4][done] [svky] Mina länkar spränger mobilbredden med 31 px - badge-pillren sticker ut

Mätt 2026-09-09 vid 390 px: document.documentElement.scrollWidth är 421. De element som sticker ut är .badge-pillren, ut till x=421.

Mätt både före och efter en ändring i samma fil samma dag, med samma värde - alltså en befintlig bugg, inte en följd av den ändringen.

Samma klass som TASK-1707, som gäller beställningssidan med 5 px. Den här är sex gånger värre.

Testdatan hade långa kortkoder (allhelgona-replay-1). Kontrollera om det är kodlängden som driver bredden eller om pillret spränger även med korta koder - svaret avgör om fixen är på pillret eller på raden det sitter i.

Klart när: scrollWidth är lika med viewportbredden vid 390 px med en lista som bär både långa och korta koder.

Verifiera: shot vid 390px OCH 1280px. Mät scrollWidth, och lista de element vars getBoundingClientRect().right överstiger clientWidth - en siffra utan att veta VAD som sticker ut leder till gissningar.

- ID: `01M236XJ5MMBD24Z3RGF5H1PFS`
- Type: bug
- Actor: ai:claude-code

---

## [P4][done] [svky] Testlistan svky-1673 har föråldrade punkter efter att Swish-länktypen revs

Sessionen http://ubuntu-ai:8890/test/svky-1673 skapades innan Swish byggdes om. Punkt 3 till 12 prövar en funktion som inte finns längre: kortlänkar med typ swish, landningssidan /kollekt och /gava, och Swish-fliken i beställningsformuläret. Allt det revs 2026-09-08 i commit f75d851.

Rasmus hann testa 7 av 34 punkter innan omtaget.

Ersätt punkterna om Swish med den generator som faktiskt byggdes: /swish och /swishqr, nedladdning av PNG och SVG, testknappen för applänken, och varningen som visas när något fält kryssas i som fritt.

Resten av listan gäller fortfarande: QR-sköldarna, samlingarnas QR, admin-gränssnittet, domänansökan, nyheter och notisbanner, och mobilbredderna.

- ID: `01M213X2YVD6GM6J3E3CPGGEAQ`
- Type: chore
- Actor: ai:claude-code

---

## [P4][todo] [svky] Beställningssidan spränger mobilbredden med 5 px

Mätt 2026-09-08: /bestall ger scrollWidth 395 i ett 390 px fönster, inloggad. Felet fanns före Swish-fliken - samma siffra med och utan den.

Överflödet ligger i tab-link, inte i typvalet. Alerten som säger 'Inloggad som <adress>' har scrollWidth 337 mot clientWidth 274, så en lång e-postadress bryter inte.

Verifiera: shot vid 390px före och efter, och att document.documentElement.scrollWidth är 390. Kolla även 320px.

- ID: `01M20ZKHHSARN33JEY4N177PTX`
- Type: bug
- Actor: ai:claude-code

---

## [P4][done] [svky] Rensa engelskan ur driftytan - allt ska vara på svenska

Driftytan blandar svenska och engelska. Statuspillren visar systemds råa ord (running, exited, success, failed, active, activating), och lägesfilens nycklar läcker igenom på sina håll. En driftyta som säger 'RUNNING' bredvid 'Utcheckning' läser ojämnt.

Översätt det som visas för en människa, men behåll de råa värdena där de är identifierare - enhetsnamn (svky-begaran-rulla-ut.service) och kommandon (systemctl reset-failed) ska stå oöversatta, annars går de inte att klistra in.

Verifiera: shot vid 390px OCH 1280px i både friskt och varningstungt läge, och att inget engelskt ord står kvar i det renderade fragmentet utanför kod- och enhetsnamn.

- ID: `01M1YX7WQNRPTEZNZ29PN6YVN1`
- Type: improvement
- Actor: ai:claude-code

---

## [P4][todo] [svky] Visa reserverade koder för admin i admin-UI:t

RESERVED_CODES i app/config.py är osynlig i driften - en admin som skapar en kortlänk ser inte vilka koder som är upptagna av systemet förrän valideringen nekar. Visa listan någonstans i admin-UI:t (egen liten sida eller ett avsnitt under en befintlig admin-vy). Verifiera: shot vid 390px OCH 1280px, och att listan matchar RESERVED_CODES i koden i stället för en handskriven kopia.

- ID: `01M1YV275W50Q0MJW0PDTC4CEH`
- Type: feature
- Actor: ai:claude-code

---

## [P4][done] [svky] Se över driftytans UI: utnyttja desktopbredden och komprimera knapparna

Driftytan lägger korten i en smal kolumn - på desktop finns gott om bredd som inte används, så mer information får plats utan att man skrollar. Knapparna tar också mycket höjd: knapptexterna (Hämta driftkod, Rulla ut drift/) är självförklarande, så den förklarande brödtexten under varje knapp kan kortas eller döljas. Verifiera med shot vid 390px OCH 1280px - ingen horisontell overflow, och alla kort synliga utan skroll på desktop.

- ID: `01M1YTZ4RN05BWAS8XKXG447HY`
- Type: improvement
- Actor: ai:claude-code

---

## [P4][done] [svky] Ge driftytan ett eget kort bredvid staging och produktion

## Context

Rasmus 2026-09-07. Ytan visar två kort: Staging och Produktion. Driftytan själv - alltså koden som ritar sidan och jobben bakom knapparna - har inget kort.

Uppgifterna FINNS redan i lägesfilen under drift: efter, amne, fel, outrullade, olasbara. Men de renderas bara som VARNINGAR när något är fel. Går allt bra säger sidan ingenting alls om sig själv, medan de andra två miljöerna alltid har ett kort med digest, commit och status.

Asymmetrin gör att man inte kan svara på 'vilken driftkod kör den här sidan' utan att något är trasigt.

## Vad kortet ska visa

Samma form som de andra två, så raden med tre kort läses likadant:

- Commit som utcheckningen står på (drift-fältens underlag)
- Status som pill: i fas / ligger efter / ej utrullad / okänt
- Vid 'ligger efter': hur många commitar och ämnesraden, som i dag
- Vid 'ej utrullad': vilka kopior som skiljer sig

## Vad som INTE ska hända

- Varningsraderna ska inte dupliceras. Kortet bär det normala läget, raderna bär undantagen. Står allt rätt ska INGEN driftkodsrad synas ovanför korten - bara kortet
- Rutnätet är i dag två kolumner vid 700px och en under. Tre kort kräver ett val: tre kolumner på bred skärm, eller två plus ett som spänner. Välj det som håller korten lika breda - de var 38 px smala tidigare och det åtgärdades med box-sizing, återinför inte problemet
- Ingen ny datainsamling. Allt finns i drift-fältet

## Acceptance criteria

- [ ] Tre kort i rutnätet: Staging, Produktion, Driftytan
- [ ] Kortet visar commit och en status-pill med samma klasser som de andra (.pill.ok / .pill.fel)
- [ ] När allt är i fas syns INGEN driftkodsvarning ovanför korten, bara kortets pill
- [ ] Vid fel står orsaken kvar i varningsraden, med samma ordning efter allvar som i dag
- [ ] Kortbredden är oförändrad mot sektionerna under, mätt i webbläsare
- [ ] Fungerar vid 390 px utan horisontell scroll

## Verification

- Playwright vid 1280 och 390 px: mät att kortens högerkant är samma som understa sektionens, och att scrollWidth är högst 390 vid 390 px
- Prov för alla fyra lägena: i fas, ligger efter, ej utrullad, okänt
- Prov som faller om varningsraden visas samtidigt som kortet säger i fas

Görs i SAMMA svep som TASK-1698 - båda rör drift/svky-driftyta.py, och tre omgångar redigeringar i samma fil är onödigt. Blockerad tills TASK-1697 landat.

- ID: `01M1YSSJ9RA66NTWT2Y3RQB75X`
- Type: improvement
- Actor: human:rasmus

---

## [P4][done] [svky] Jobbets slutbesked talar alltid om staging, oavsett vilken knapp som trycktes

## Context

Hittad 2026-09-07 genom kopieringsknappens felsökningsdata.

foljUppJobb() i drift/svky-driftyta.py jämför alltid stagings digest före och efter (rad ~440), och skriver annars 'Klart. Ingen ny version - staging kör redan senaste bygget'.

Det stämde när det fanns EN knapp. Nu finns fyra operationer, och tre av dem har ingenting med stagings digest att göra:

- hamta-driftkod: stagings digest ändras aldrig, så beskedet blir alltid 'ingen ny version' även när hämtningen faktiskt hämtade två commitar
- rulla-ut: samma sak
- promotera: det är PRODUKTIONENS digest som ändras, inte stagings

Följden är ett besked som säger fel sak med självförtroende, vilket är sämre än inget besked.

## Andra fyndet i samma svep

Kopieringsknappen läser de synliga meddelandena ur DOM:en och rådatan från /lage.json i två skilda anrop. Ett verkligt fall 2026-09-07: fragmentet var tre sekunder gammalt och sa 'ligger 2 commitar efter' medan rådatan sa efter: 0. Båda var korrekta var för sig, men tillsammans ser det ut som en motsägelse - och hela poängen med knappen är att skillnaden mellan vad servern tyckte och vad användaren såg ska vara meningsfull.

## Acceptance criteria

- [ ] Slutbeskedet väljs per operation. Jämför stagings digest för uppdatera, produktionens för promotera, drift.efter för hamta-driftkod och drift.outrullade för rulla-ut
- [ ] Fälten som behövs finns i tillstand-spannet (id=tillstand), som i dag bara bär vantande, aktiv och staging
- [ ] 'Ingen förändring' är fortfarande ett SVAR och inte tystnad, men formulerat för rätt operation
- [ ] Kopieringen hämtar fragmentet på nytt innan den läser DOM:en, så meddelanden och rådata kommer från samma ögonblick
- [ ] Den kopierade texten bär lägesfilens hamtad-tidsstämpel, så en kvarvarande skillnad SYNS i stället för att förvirra

## Verification

- Playwright: tryck varje knapp mot ett läge där dess egen storhet är oförändrad, och kontrollera att beskedet nämner rätt sak. Provet ska FALLA om jämförelsen görs mot stagings digest för alla fyra
- Kopiera felsökningsdata och bekräfta att hamtad-raden finns med

Blockerad tills TASK-1697 landat - codex arbetar i samma fil.

- ID: `01M1YSNH84H8B6FTN6XJ982HRK`
- Type: bug
- Actor: human:rasmus

---

## [P4][done] [svky] Åtgärda UX-granskningens kvarvarande fynd på driftytan

## Context

UX-granskningen av driftytan ligger som doc 01M1YRTRFH4JQR0PF6YHEZVV9S. De tre viktigaste fynden är redan åtgärdade i 8c0bff2: kraschen på fel datatyp, radernas ordning, och den engelska valideringsbubblan.

Det som återstår är mindre men konkret. Ingenting här är en bugg - det är slipning av en yta som redan fungerar. Granskaren lyfte också fram flera saker som redan är bra, se docens sista avsnitt: rör inte serverrenderingen av fragmentet, 303-omdirigeringen efter POST, X-Fragment-huvudet eller jobbuppföljningen.

## Acceptance criteria

- [ ] Statusraden (#status) har aria-live=polite. Sidan byter hela #innehall var tionde sekund via innerHTML utan att meddela hjälpmedel, och statusraden är den enda plats som sammanfattar vad som hänt
- [ ] Raden 'Ett nyare bygge finns än det staging kör' säger vad som händer härnäst. Den har ingen knapp att hänvisa till - staginguppdateraren hämtar den automatiskt - så en halv mening räcker: annars läser den som ett problem utan väg framåt
- [ ] label i promotera-formuläret får flex-basis 100% i stil med .hjalp, så kryssruta och knapp inte bryts isär på 390px vid en slumpmässig ordbrytningspunkt
- [ ] Kontrasten på .saknas verifierad mot BÅDA bakgrunderna den förekommer på: vit kortbakgrund och .pill.fel:s rosa. Granskaren mätte 2.8:1 respektive 2.17:1, kravet är 4.5:1. En första fix finns redan i 8c0bff2 - kontrollera att den räcker, ändra annars
- [ ] Automatik-kortet tar lika mycket plats som statuskorten trots att det är bekräftelse och inte huvudfråga. Gör det mindre framträdande UTAN att dölja något

## Icke-mål

- Historik över promoteringar (docens avsnitt 7). Det kräver att något börjar skriva en logg och är en egen uppgift, inte en UX-slipning
- Åldersstämpel per delfält
- Ingen ny CSS-ram, inget npm, inga beroenden. Ytan är ren stdlib med flit: ett driftverktyg som beror på appens beroenden kan gå sönder av samma sak som det ska felsöka

## Verification

- pytest tests/test_driftyta.py -q ska gå igenom, och nya prov ska läggas för de kriterier som går att mäta i markup
- Kontrasten mätes, inte uppskattas. Räkna kvoten ur de faktiska hex-värdena
- Playwright vid 390 px: kryssruta och knapp på samma rad eller medvetet på var sin, inte slumpmässigt brutna. document.documentElement.scrollWidth högst 390
- Playwright: inga sidfel (pageerror) vid laddning

- ID: `01M1YS7303GQEKAHH43NNSTYS6`
- Type: improvement
- Actor: human:rasmus

---

## [P4][done] [svky] Sidhuvudet spränger mobilbredden för inloggade

## Context

Hittad 2026-09-07 under QR-arbetet, i en mätning som skulle kontrollera något annat.

Vid 390 px är document.scrollWidth 441 på /mina-lankar. Det som sticker ut är nav och a.btn-logout i sidhuvudet - alltså base.html, inte någon enskild sida. Gäller varje sida för en INLOGGAD användare, eftersom btn-logout bara finns då.

Följden är horisontell scroll på hela tjänsten på telefon. Ingen funktion går sönder, men listan går att dra i sidled och innehållet hamnar snett.

Mätt både med och utan QR-rutan öppen: 441 i båda fallen, så det är inte QR-koden som orsakar det.

## Acceptance criteria

- [ ] document.documentElement.scrollWidth är högst 390 vid 390 px viewport, inloggad, på /mina-lankar, /bestall och startsidan
- [ ] Navigeringen är fortfarande användbar - lösningen får inte vara att dölja Logga ut

## Verification

- Playwright vid 390 px, inloggad: document.documentElement.scrollWidth <= 390 på de tre sidorna
- Kontrollera också vid 1280 px att inget ändrades där

- ID: `01M1YMY3J75SASXEZMCF80ERZP`
- Type: bug
- Actor: human:rasmus

---

## [P4][done] [svky] Knapp på driftytan som kollar efter ny version direkt

## Context

Timern kollar var femte minut. Sitter Rasmus och utvecklar vill han kunna prova snabbare än så, utan att ssh:a in och köra systemctl.

Knappen gör INGET nytt: den startar samma jobb som timern startar. Hela logiken - hämta digest, verifiera signatur, byta, vänta på health - ligger redan i drift/svky-uppdatera-staging.sh och ska inte dupliceras.

## Formen är en säkerhetsegenskap

Knappen tar INGEN parameter. Den kan inte peka ut en digest, en tagg, en container eller ett kommando. Vilken operation som avses avgörs av vilken knapp som trycktes, och vad operationen gör står i koden.

Det är samma princip som slöjdas kontrollplan: 'Kontrollplanet kan inte ta emot kommandon, sökvägar, databasnamn eller image-digests. Varje operation är ett verb utan argument.' Se backlog-docen Staging och promotion: underlag från slöjda.de.

Driftytan får inte köra som root. En rad i sudoers, utan wildcard, räcker för svky:

    svky-ops ALL=(root) NOPASSWD: /usr/bin/systemctl start svky-staging-uppdatera.service

Ett wildcard i sökvägen eller ett argument från webben gör raden till en godtycklig kommandokörning som root.

Knappen får INTE ligga i svky-appens adminyta. Kan appen starta jobb på värden blir ett appintrång detsamma som root - se kommentaren på TASK-1087.

## Acceptance criteria

- [ ] Driftytan (egen tjänst, tailnet-only) har en knapp som startar svky-staging-uppdatera.service
- [ ] Knappen tar inga argument, och sudoers-raden har inget wildcard
- [ ] Ytan visar utfallet: pågår, klart, eller misslyckades med orsak
- [ ] Ett jobb åt gången - trycks knappen medan jobbet kör ska den säga det, inte köa

## Verification

- Tryck knappen, se att journalen visar en körning startad av driftytans användare
- Försök starta något ANNAT genom samma väg och bekräfta att sudo nekar
- Tryck två gånger snabbt och bekräfta att bara ett jobb körs (flock finns redan i skriptet)

Beror på TASK-1087 steg 5: driftytan finns inte än.

- ID: `01M1YDCTQJ6ZY4C6QCAB90Y5QM`
- Type: feature
- Actor: human:rasmus

---

## [P4][todo] [svky] Autostarta tmux vid ssh till svky-server

Rasmus 2026-09-07. Interaktiv ssh till svky-server ska landa direkt i en tmux-session, så att ett avbrutet nätverk inte tar med sig ett pågående arbete.

Förlagan finns på slöjda-servern: interaktiv ssh ansluter automatiskt till tmux och arbetskatalogen. Se docs/ci-cd.md i ~/workspace/hemslojden/anmälningssystem.

Viktigt: ICKE-interaktiv ssh får inte gå via tmux. Det är den vägen en framtida deploy använder (TASK-1087 steg 4), och en tmux-anslutning där hänger eller ger oläsbar utdata.

Klart när / Verifiera:
- ssh svky-server landar i tmux, och en ny ssh återansluter till samma session i stället för att skapa en ny
- ssh svky-server 'echo prov' skriver prov och inget annat, alltså ingen tmux
- Arbetskatalogen är ~/svk-short

- ID: `01M1Y6E0P732FKXM6BSCEDX9AK`
- Type: chore
- Actor: human:rasmus

---

## [P4][todo] [svky] Lås GitHub Actions till full commit-SHA i stället för tagg

## Context

Workflowen använder rörliga taggar: actions/checkout@v4, docker/build-push-action@v5, sigstore/cosign-installer@v3 och flera till. En tagg kan flyttas av den som äger actionen, så en granskad version är inte samma sak som den som körs nästa gång.

Det blev mer angeläget när signeringen infördes (TASK-1087 steg 3). Cosign-installer kör i ett jobb som har id-token: write - alltså rätten att hämta det OIDC-token hela signeringskedjan vilar på.

Slöjda låser alla externa actions till full SHA, med en kommentar som anger vilken granskad release respektive SHA motsvarar.

## Acceptance criteria

- [ ] Alla externa actions i .github/workflows/ pinnade till full commit-SHA
- [ ] Kommentar per rad som anger vilken release SHA:n motsvarar
- [ ] Ett grönt bygge efter ändringen

## Verification

- grep -n 'uses:' .github/workflows/*.yml ska inte visa någon @v-tagg
- Bygget på main går igenom, och signaturen verifieras som förut

- ID: `01M1Y6A8636DAXP57QCNYQAJBV`
- Type: improvement
- Actor: human:rasmus

---

## [P4][todo] [svky] Byt till TemplateResponse nya signatur, 111 deprecation-varningar

## Context

Testsviten (TASK-1678) visar 111 DeprecationWarning från Starlette: TemplateResponse(name, {"request": request}) är den gamla ordningen, den nya är TemplateResponse(request, name). Det fungerar än, men försvinner i en framtida Starlette-version och dränker verklig varningsutdata i proven under tiden.

## Acceptance criteria

- [ ] Alla anrop använder nya ordningen
- [ ] pytest -q visar inga Starlette-deprecationvarningar kvar

## Verification

- pytest -q 2>&1 | grep -c DeprecationWarning ska ge 0
- Sidorna renderar som förut, kontrollera startsida, /bestall och /mina-lankar i webbläsare

- ID: `01M1XWGZQN6CYDAMW2SNRWDYQE`
- Type: chore
- Actor: human:rasmus

---

## [P4][todo] [svky] Sätt request_body max_size i Caddy

## Context

Caddyfile har ingen gräns för hur stor en request body får vara. Längdgränserna i app/validation.py skyddar fälten, men de läses först efter att hela kroppen tagits emot. En stor POST binder alltså minne och tid i uvicorn innan valideringen hinner säga nej.

Detta var en av de öppna frågorna i granskningen 2026-08-20 och besvarades med att ingen gräns finns.

## Acceptance criteria

- [ ] request_body max_size satt i Caddyfile, med en kommentar om vald siffra
- [ ] Gränsen är rymlig nog för det största legitima formuläret (markdown-kroppar, MAX_BODY_LENGTH är 20000 tecken)

## Verification

- curl med en body över gränsen ska ge 413 från Caddy, inte nå appen
- curl med en normal beställning ska fungera som förut

- ID: `01M1XWGZQFMJSA2EN4CB5WWXYJ`
- Type: improvement
- Actor: human:rasmus

---

## [P4][todo] [svky] Enhetliga statuskoder när överlåtelsespärren slår till

## Context

De tre överlåtelse-endpointsen svarar olika när rate limit slår till: links.py ger 429, account.py 422 och bundles.py en 303 med meddelande i query. Spärren fungerar överallt, men en klient kan inte behandla dem lika, och den som läser koden tror att de gör olika saker.

## Acceptance criteria

- [ ] Samma statuskod för samma tillstånd i alla tre, eller en skriven motivering i koden till varför de skiljer sig
- [ ] Användaren får ett begripligt besked i alla tre fallen

## Verification

- Prov som triggar spärren på alla tre och jämför statuskoderna

- ID: `01M1XWGZQ9Q0RBTE33APNMS75N`
- Type: improvement
- Actor: human:rasmus

---

## [P4][done] [svky] Changelog-sida som visar vad som ändrats i verktyget

Det finns ingen changelog i dag, varken fil i repot eller sida i appen. Användarna ser aldrig vad som är nytt.

Omfattning:
- Publik sida, t.ex. /nyheter eller /changelog, länkad från footern.
- Innehållet redigeras av admin på samma sätt som /admin/om (markdown i site_settings), eller läses från en CHANGELOG-fil i repot. Välj det ena, blanda inte.
- Hänger ihop med notisbannern: en banner om en nyhet bör kunna länka hit.

Klart när / Verifiera:
- Sidan går att nå som utloggad och renderar markdown.
- Länken i footern fungerar från alla sidor.
- Kontrollera i webbläsare vid 390 px och 1280 px.

- ID: `01M1XK0D2ZGMYN0Y0ECE5GDQRE`
- Type: feature
- Actor: human:rasmus

---

## [P4][done] [svky] Notisbanner som admin kan sätta för alla användare

Admin ska kunna lägga upp ett meddelande som visas för alla besökare i svky.se, för nyheter, kommande driftstopp och liknande.

Omfattning:
- Redigeras under admin, samma mönster som /admin/om och /admin/integritet. Texten kan bo i site_settings (key/value finns redan).
- Nivå på bannern (info, varning) styr färg.
- Bannern går att slå av utan att texten tappas, och kan ha ett slutdatum så att en driftstoppsnotis försvinner av sig själv.
- Visas i base.html så den slår igenom på alla sidor. Besökaren ska kunna stänga den för egen del.

Klart när / Verifiera:
- Sätt en banner som admin, besök startsidan som utloggad och se den.
- Stäng den och bekräfta att den är borta efter omladdning.
- Sätt ett slutdatum bakåt i tiden och bekräfta att bannern inte visas.
- Kontrollera vid 390 px att bannern inte täcker navigeringen.

- ID: `01M1XK0D2RTC2KHM0AW1RQQCGD`
- Type: feature
- Actor: human:rasmus

---

## [P4][done] [svky] request-transfer-endpoints saknar rate limit (intern mail-spam-vektor)

Inkonsekvent rate limiting, grep-verifierad 2026-08-20.

request_transfer (user/links.py:288), begar_overlatelse (user/bundles.py:625) och request_transfer_all (user/account.py:223) anropar INTE check_rate_limit. Övriga mail-utlösande flöden gör det (login, resend, order, delete_account, takeover, bundle-takeover). Verifierat: account.py:s 2 check_rate_limit-anrop gäller delete_account, inte request_transfer_all.

Roll: inloggad användare. Repro: skapa länk, POST request-transfer upprepat med olika to_email (@svenskakyrkan.se) - varje anrop mailar utan takt-spärr. Utfall: ospärrad intern skräppost mot kollegors adresser.

Allvar lågt (kräver konto, mottagare begränsad till org-domänen), men tydlig avvikelse från kodens eget mönster.

Klart när: de tre endpointsen anropar check_rate_limit som övriga mail-flöden. Verifiera: grep check_rate_limit i de tre funktionerna ger träff.

- ID: `01M0GCPJPAN1HDZ6MAD5YNR1MX`
- Type: improvement
- Actor: ai:claude-code

---

## [P4][todo] [svky] Uppetidssond mot slojda.de, och egen check för svky.se

Andra halvan av hemslojd TASK-833, som byggde sonden. Skriptet och systemd-enheterna finns i ~/workspace/infra/uppetidssond/ och är gemensamma - ingenting behöver skrivas här.

De två servrarna bevakar varandra: sonden på svky.se-servern hämtar slojda.de, och sonden på slojda.de-servern hämtar https://svky.se/healthz. Den här tasken är den andra riktningen.

ATT GÖRA:
1. Skapa en check i svky.se-projektet på healthchecks.io, period 300 s och grace 900 s. Nyckeln ligger i secrets.fish som HEALTHCHECKS_API_KEY_SVKY - API-nycklarna är per projekt.
2. Koppla larmkanaler. ntfy-topicen för svky finns inte än; följer konventionen svc_<tjanstnamn> enligt infras notifieringspolicy och provisioneras med ntfy-provision-skillen. E-post ska vara med som reservvag - ligger TERVO2 nere nar ingen ntfy-notis fram.
3. Installera sonden pa slojda.de-servern enligt READMEn, med SOND_MAL=https://svky.se/healthz och SOND_VANTAT_SVAR för ok-true.
4. Framkalla felet och verifiera hela larmvagen. Ett testmeddelande bevisar bara att curl fungerar.

KLART NAR: svky.se har en uppetidscheck som larmar pa samma tva kanaler, och felet ar framkallat en gang.

- ID: `01KZGSFCXPCKH624AAEYVFNTMG`
- Type: feature
- Actor: human:rasmus

---

## [P5][todo] [svky] Lägg tmp/ i .gitignore

## Context

tmp/ ligger otrackad i arbetsträdet och dyker upp i varje git status. Den riskerar att sveps med i en git add -A.

## Acceptance criteria

- [ ] tmp/ i .gitignore

## Verification

- git status --short ska inte visa tmp/

- ID: `01M1XWGZQT7PKXBDS26VG2WMHE`
- Type: chore
- Actor: human:rasmus

---

