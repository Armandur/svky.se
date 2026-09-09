#!/usr/bin/env bash
# Rullar ut driftkoden: kopierar till /usr/local/bin och /etc/systemd/system.
# Startas av driftytans knapp, körs som root.
#
# install -m 644, inte cp. cp bevarar källans rättigheter, och en umask på 077
# ger rotägda 600-filer som samlaren inte kan LÄSA - den rapporterade dem då
# som olika fast de var identiska. Enhetsfiler bär inga hemligheter.
#
# Filnamnen står HÄR och läses aldrig ur en katalog. Ett steg som läser vad det
# ska installera ur någon annans fil är en godtycklig installationsprimitiv.
set -euo pipefail

ARBETSKATALOG=${SVKY_ARBETSKATALOG:-/home/rasmus/svk-short}
cd "$ARBETSKATALOG"

logga() { echo "[$(date -Is)] $*"; }

# Jobbet kör som ROOT i en utcheckning rasmus äger, och git vägrar då med
# "detected dubious ownership" och exit 128. Med set -e dödade det skriptet
# EFTER att filerna installerats men FÖRE omstarterna - en halvkörd
# utrullning, exakt det den här filen har kommentarer om att undvika.
# safe.directory sätts per anrop, inte i en global konfiguration: skyddet ska
# inte bero på vem som råkar äga katalogen i framtiden.
git_() { git -c safe.directory="$ARBETSKATALOG" "$@"; }

ENHETER="
svky-driftyta.service
svky-samla-lage.service
svky-samla-lage.timer
svky-staging-uppdatera.service
svky-staging-uppdatera.timer
svky-begaran-uppdatera.path
svky-begaran-uppdatera.service
svky-begaran-promotera.path
svky-begaran-promotera.service
svky-begaran-hamta-driftkod.path
svky-begaran-hamta-driftkod.service
svky-begaran-rulla-ut.path
svky-begaran-rulla-ut.service
svky-begaran-inloggningslankar.path
svky-begaran-inloggningslankar.service
"

# Path-enheterna, som måste vara ENABLE:ade för att plocka upp något efter en
# omstart av servern. daemon-reload räcker inte, och restart nedan startar dem
# bara den här gången - en ny enhet hade fungerat tills servern bootade om och
# sedan varit en tyst död knapp. enable är idempotent, så listan får stå kvar.
PATHENHETER="
svky-begaran-uppdatera.path
svky-begaran-promotera.path
svky-begaran-hamta-driftkod.path
svky-begaran-rulla-ut.path
svky-begaran-inloggningslankar.path
"

install -m 755 drift/svky-driftyta.py /usr/local/bin/svky-driftyta
logga "Installerade /usr/local/bin/svky-driftyta"

for e in $ENHETER; do
    [ -f "drift/systemd/$e" ] || { logga "SAKNAS i repot: $e"; continue; }
    install -m 644 "drift/systemd/$e" "/etc/systemd/system/$e"
done
logga "Installerade $(echo "$ENHETER" | grep -c .) enheter"

systemctl daemon-reload
# shellcheck disable=SC2086
systemctl enable $PATHENHETER >/dev/null 2>&1 || logga "VARNING: kunde inte enable:a alla path-enheter"

# Skriv ner vad som rullades ut. Utan den här filen går det inte att svara
# på "vilken kod kör de rotägda kopiorna" annat än genom att jämföra filer -
# och en jämförelse säger bara om de skiljer sig, inte VAD som saknas.
#
# FÖRE omstarterna: en omstart som faller får inte ta med sig uppgiften om
# vad som faktiskt hann rullas ut.
COMMIT=$(git_ rev-parse HEAD)
install -d -m 755 /var/lib/svky
printf '%s\n' "$COMMIT" > /var/lib/svky/utrullat
chmod 644 /var/lib/svky/utrullat


# Starta om det som kör långlivat. De kortlivade jobben läser sin enhet när de
# startar, men en långlivad tjänst sitter kvar på den konfiguration den läste -
# enable --now startar INTE om något som redan kör.
#
# --no-block på driftytan: den är sidan som visar att det här jobbet kör, och
# en synkron omstart klipper anslutningen mitt i medan skriptet väntar på att
# den kommer upp igen. Med --no-block hinner jobbet skriva klart sitt sista
# loggmeddelande och avsluta först.
# shellcheck disable=SC2086
systemctl restart $PATHENHETER 2>/dev/null || true
systemctl restart --no-block svky-driftyta.service

logga "Utrullat från $(git_ rev-parse --short=8 HEAD)"
