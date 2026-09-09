#!/usr/bin/env bash
# Skapar färska inloggningslänkar till STAGING: en admin och en vanlig
# användare. Startas av driftytans knapp, körs som root.
#
# Genvägen, inte ersättningen. Den vanliga vägen in i staging går fortfarande
# via Mailpit: beställ en magic link i appen och läs mailet på 8444. Den
# vägen fungerar och försvinner inte. Det här skriptet finns för att slippa
# tre klick när man snabbt vill se en vy som två roller.
#
# Länkarna är ENGÅNGSBRICKOR, som alla magic links. En använd länk ger
# "Den här länken har redan använts" - tryck på knappen igen för nya. Därför
# skriver skriptet en tidsstämpel bredvid dem. Då kan ytan säga hur gamla de
# är, i stället för att visa två länkar som ser giltiga ut fast de är brända.
set -euo pipefail

STAGING_CONTAINER=${SVKY_STAGING_CONTAINER:-svky-staging-svky-1}
UT=${SVKY_INLOGGNINGSFIL:-/var/lib/svky/inloggningslankar.json}
BAS=${SVKY_URL_STAGING:-https://svky-server.ussuri-tawny.ts.net:8443}
ADMIN_EPOST=${SVKY_STAGING_ADMIN:-admin@staging.svky.se}
ANVANDARE_EPOST=${SVKY_STAGING_ANVANDARE:-anvandare@staging.svky.se}
TIMMAR=${SVKY_INLOGGNING_TIMMAR:-24}

logga() { echo "[$(date -Is)] $*"; }

# --- Bekräfta att containern ÄR staging ---------------------------------
# Containernamnet kommer ur miljön och kan vara fel. En tokenskrivare som går
# att peka om är en admin-bakdörr till produktionen, så namnet får inte vara
# det enda som skiljer dem åt. Staging monterar ./data-staging på /app/data
# och produktionen ./data. Skriptet kontrollerar den skillnaden.
KALLA=$(docker inspect --format \
    '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}' \
    "$STAGING_CONTAINER" 2>/dev/null) || {
    logga "FEL: hittade ingen container vid namn $STAGING_CONTAINER."
    exit 1
}

case "$KALLA" in
    */data-staging)
        ;;
    *)
        logga "AVBRYTER: $STAGING_CONTAINER monterar '$KALLA' på /app/data, inte en"
        logga "katalog som slutar på data-staging. Skriptet skriver inloggningstokens"
        logga "och får bara röra stagingdatabasen."
        exit 1
        ;;
esac

logga "Staging bekräftad: $STAGING_CONTAINER monterar $KALLA"

# --- Skapa användarna och brickorna -------------------------------------
# Körs INNE i containern, mot dess egen databas. Att nå filen från värden
# hade krävt att skriptet vet var volymen ligger och att sqlite3 finns där -
# containern har både appen och sin databas.
#
# Skriptet går in på stdin och tar inga argument från oss. E-postadresserna
# reser som miljövariabler, så ingenting vi läser ur miljön hamnar i en
# kodsträng.
JSON=$(docker exec -i \
    -e SVKY_ADMIN="$ADMIN_EPOST" \
    -e SVKY_ANVANDARE="$ANVANDARE_EPOST" \
    -e SVKY_TIMMAR="$TIMMAR" \
    "$STAGING_CONTAINER" python3 - <<'PY'
import json
import os
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

sokvag = os.environ.get("DATABASE_PATH", "data/links.db")
timmar = int(os.environ["SVKY_TIMMAR"])
db = sqlite3.connect(sokvag)
db.row_factory = sqlite3.Row

# Utgångstiden ligger naivt i UTC, som resten av tabellen. En tidszonsmedveten
# sträng här hade fallit på datetime.fromisoformat-jämförelsen i auth.py.
nu = datetime.now(UTC).replace(tzinfo=None)
gar_ut = (nu + timedelta(hours=timmar)).isoformat(timespec="seconds")

ut = []
for roll, epost, admin in (
    ("Admin", os.environ["SVKY_ADMIN"], 1),
    ("Vanlig användare", os.environ["SVKY_ANVANDARE"], 0),
):
    db.execute("INSERT OR IGNORE INTO users (email, is_admin) VALUES (?,?)", (epost, admin))
    # Skriptet sätter rättigheten även för en användare som redan fanns.
    # Annars kunde admin-knappen ge en session utan adminrättigheter, beroende
    # på vad någon råkat skapa i stagingdatabasen tidigare.
    db.execute("UPDATE users SET is_admin=? WHERE email=?", (admin, epost))
    rad = db.execute("SELECT id FROM users WHERE email=?", (epost,)).fetchone()

    # Städa användarens obrukade brickor. Utan det växer tokens-tabellen med
    # en rad per knapptryck, och de gamla duger ändå inte så fort ytan visar
    # en ny länk.
    db.execute(
        "DELETE FROM tokens WHERE user_id=? AND purpose='login' AND used_at IS NULL",
        (rad["id"],),
    )
    bricka = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO tokens (token, user_id, link_id, purpose, expires_at) "
        "VALUES (?,?,NULL,'login',?)",
        (bricka, rad["id"], gar_ut),
    )
    ut.append({"roll": roll, "epost": epost, "bricka": bricka})

db.commit()
print(json.dumps(ut))
PY
) || { logga "FEL: kunde inte skapa brickor i $STAGING_CONTAINER."; exit 1; }

# --- Skriv filen ytan läser ----------------------------------------------
# 644 uttryckligen, av samma skäl som körmarkörerna: ytan kör som en annan
# användare och en fil den inte kan läsa är samma sak som ingen fil alls.
install -d -m 755 "$(dirname "$UT")"
TMP=$(mktemp)
BAS="$BAS" TIMMAR="$TIMMAR" python3 - "$JSON" > "$TMP" <<'PY'
import json
import os
import sys
from datetime import UTC, datetime

bas = os.environ["BAS"].rstrip("/")
poster = json.loads(sys.argv[1])
print(json.dumps({
    "skapad": datetime.now(UTC).isoformat(timespec="seconds"),
    "giltiga_timmar": int(os.environ["TIMMAR"]),
    "lankar": [
        {"roll": p["roll"], "epost": p["epost"], "url": f"{bas}/auth/{p['bricka']}"}
        for p in poster
    ],
}, ensure_ascii=False))
PY
install -m 644 "$TMP" "$UT"
rm -f "$TMP"

logga "Skrev $(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["lankar"]))' "$UT") inloggningslänkar till $UT"
