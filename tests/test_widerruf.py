"""Trennen und Entfernen widerrufen den Zugang bei TMDB (Attrappe, kein echter Dienst)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.streaming_finder import quellen
from custom_components.streaming_finder.const import CONF_KONTO_ID, CONF_KONTO_SITZUNG, CONF_KONTO_TOKEN, CONF_KONTO_V3, DOMAIN

KONTO = {"tmdb_token": "x" * 50, CONF_KONTO_TOKEN: "konto", CONF_KONTO_ID: "1", CONF_KONTO_SITZUNG: "sitzung", CONF_KONTO_V3: 7}


async def test_widerruf_ruft_beide_endpunkte(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.delete(f"{quellen.TMDB_URL}/authentication/session", json={"success": True})
    aioclient_mock.delete(f"{quellen.TMDB4_URL}/auth/access_token", json={"success": True})
    assert await quellen.zugang_widerrufen(async_get_clientsession(hass), "x" * 50, "sitzung", "konto")
    aufrufe = {(m, str(u), str(d)) for m, u, d, _h in aioclient_mock.mock_calls}
    assert ("DELETE", f"{quellen.TMDB_URL}/authentication/session", "{'session_id': 'sitzung'}") in aufrufe
    assert ("DELETE", f"{quellen.TMDB4_URL}/auth/access_token", "{'access_token': 'konto'}") in aufrufe


async def _trennen(hass: HomeAssistant, eintrag: MockConfigEntry, widerruf: AsyncMock) -> dict:
    with patch.object(quellen, "zugang_widerrufen", widerruf):
        ergebnis = await hass.config_entries.options.async_init(eintrag.entry_id)
        ergebnis = await hass.config_entries.options.async_configure(ergebnis["flow_id"], {"next_step_id": "trennen"})
        return await hass.config_entries.options.async_configure(ergebnis["flow_id"], {}), ergebnis["flow_id"]


async def test_trennen_widerruft(hass: HomeAssistant) -> None:
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE"}, options=KONTO)
    eintrag.add_to_hass(hass)
    widerruf = AsyncMock(return_value=True)
    with patch("custom_components.streaming_finder.async_setup_entry", return_value=True):
        ergebnis, _ = await _trennen(hass, eintrag, widerruf)
    assert ergebnis["type"] is FlowResultType.CREATE_ENTRY
    widerruf.assert_awaited_once()
    assert widerruf.await_args.args[2:] == ("sitzung", "konto")
    assert CONF_KONTO_SITZUNG not in eintrag.options


async def test_trennen_meldet_gescheiterten_widerruf(hass: HomeAssistant) -> None:
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE"}, options=KONTO)
    eintrag.add_to_hass(hass)
    widerruf = AsyncMock(return_value=False)
    with patch("custom_components.streaming_finder.async_setup_entry", return_value=True):
        ergebnis, flow = await _trennen(hass, eintrag, widerruf)
        assert ergebnis["errors"] == {"base": "widerruf_gescheitert"}
        with patch.object(quellen, "zugang_widerrufen", widerruf):
            ergebnis = await hass.config_entries.options.async_configure(flow, {})
    assert ergebnis["type"] is FlowResultType.CREATE_ENTRY  # zweites Senden trennt trotzdem
    assert widerruf.await_count == 1


async def test_entfernen_widerruft(hass: HomeAssistant) -> None:
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE"}, options=KONTO)
    eintrag.add_to_hass(hass)
    widerruf = AsyncMock(return_value=True)
    with patch.object(quellen, "zugang_widerrufen", widerruf):
        await hass.config_entries.async_remove(eintrag.entry_id)
    widerruf.assert_awaited_once()
