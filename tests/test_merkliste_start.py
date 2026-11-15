"""#10 verwaister Konto-Token, #11 Start wartet nicht auf die Merkliste (Attrappen, kein TMDB)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.streaming_finder import quellen
from custom_components.streaming_finder.const import CONF_KONTO_ID, CONF_KONTO_SITZUNG, CONF_KONTO_TOKEN, CONF_KONTO_V3, DOMAIN
from custom_components.streaming_finder.merkliste import GLEICHZEITIG, MerklisteKoordinator

KONTO = {"tmdb_token": "x" * 50, CONF_KONTO_TOKEN: "konto", CONF_KONTO_ID: "1", CONF_KONTO_SITZUNG: "sitzung", CONF_KONTO_V3: 7}


async def test_gescheiterte_sitzung_widerruft_konto_token(hass: HomeAssistant) -> None:
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE"}, options={"tmdb_token": "x" * 50})
    eintrag.add_to_hass(hass)
    anfordern = AsyncMock(side_effect=["anfrage1", "anfrage2"])
    widerruf = AsyncMock(return_value=True)
    with (
        patch("custom_components.streaming_finder.async_setup_entry", return_value=True),
        patch.object(quellen, "freigabe_anfordern", anfordern),
        patch.object(quellen, "freigabe_abholen", AsyncMock(return_value=("neu-konto", "2"))),
        patch.object(quellen, "sitzung_aus_konto_token", AsyncMock(side_effect=quellen.QuellenFehler("kaputt"))),
        patch.object(quellen, "zugang_widerrufen", widerruf),
    ):
        ergebnis = await hass.config_entries.options.async_init(eintrag.entry_id)
        ergebnis = await hass.config_entries.options.async_configure(ergebnis["flow_id"], {"next_step_id": "konto"})
        ergebnis = await hass.config_entries.options.async_configure(ergebnis["flow_id"], {})
    assert ergebnis["errors"] == {"base": "nicht_freigegeben"}
    widerruf.assert_awaited_once()
    assert widerruf.await_args.args[2:] == (None, "neu-konto")
    assert anfordern.await_count == 2  # neue Anfrage, der neue Link steht im Formular
    assert "anfrage2" in ergebnis["description_placeholders"]["link"]
    assert CONF_KONTO_TOKEN not in eintrag.options


async def test_start_wartet_nicht_auf_die_merkliste(hass: HomeAssistant) -> None:
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE"}, options=KONTO)
    eintrag.add_to_hass(hass)
    frei = asyncio.Event()

    async def langsam(*_args):
        await frei.wait()
        return [{"id": 1, "name": "Serie", "first_air_date": "2020-01-01"}]

    with (
        patch.object(quellen, "merkliste", side_effect=langsam),
        patch("custom_components.streaming_finder.finder.Finder.angebote", AsyncMock(return_value=None)),
        patch.object(MerklisteKoordinator, "_termine", AsyncMock(return_value=[])),
    ):
        async with asyncio.timeout(5):
            assert await hass.config_entries.async_setup(eintrag.entry_id)
        assert eintrag.state is ConfigEntryState.LOADED
        assert eintrag.runtime_data.merkliste.data is None  # noch nicht geladen, Start trotzdem fertig
        frei.set()
        await hass.async_block_till_done(wait_background_tasks=True)
    assert eintrag.runtime_data.merkliste.last_exception is None, eintrag.runtime_data.merkliste.last_exception
    assert [e["titel"] for e in eintrag.runtime_data.merkliste.data] == ["Serie", "Serie"]


async def test_abrufe_gebuendelt_und_in_reihenfolge() -> None:
    laufend = hoechst = 0

    async def abruf(n: int) -> int:
        nonlocal laufend, hoechst
        laufend += 1
        hoechst = max(hoechst, laufend)
        await asyncio.sleep(0.001)
        laufend -= 1
        return n

    assert await MerklisteKoordinator._gebuendelt([abruf(n) for n in range(30)]) == list(range(30))
    assert hoechst == GLEICHZEITIG
