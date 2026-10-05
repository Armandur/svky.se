"""Admin ser systemets reserverade koder i skapa-länk-vyn, ur app.config och
inte ur en handskriven lista."""

import re

from app.config import RESERVED_CODES


def test_skapa_lank_listar_varje_reserverad_kod(client, admin):
    html = client.get("/admin/links/create").text
    listade = set(re.findall(r"<code>([^<]+)</code>", html))
    assert RESERVED_CODES <= listade
    assert f"{len(RESERVED_CODES)} koder är reserverade" in html
