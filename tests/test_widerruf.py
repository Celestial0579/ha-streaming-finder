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


async def test_verbunden_bietet_nur_trennen(hass: HomeAssistant) -> None:
    """GHSA-x2rg-wgwm-x389: Neu verbinden ohne Trennen ließe die alte Sitzung bei TMDB gültig."""
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE"}, options=KONTO)
    eintrag.add_to_hass(hass)
    ergebnis = await hass.config_entries.options.async_init(eintrag.entry_id)
    assert ergebnis["menu_options"] == ["schluessel", "trennen"]
    eintrag2 = MockConfigEntry(domain=DOMAIN, data={"land": "AT"}, options={"tmdb_token": "x" * 50})
    eintrag2.add_to_hass(hass)
    ergebnis = await hass.config_entries.options.async_init(eintrag2.entry_id)
    assert ergebnis["menu_options"] == ["schluessel", "konto"]


async def _bis_konto(hass: HomeAssistant, eintrag: MockConfigEntry) -> str:
    ergebnis = await hass.config_entries.options.async_init(eintrag.entry_id)
    ergebnis = await hass.config_entries.options.async_configure(ergebnis["flow_id"], {"next_step_id": "konto"})
    assert ergebnis["step_id"] == "konto"
    return ergebnis["flow_id"]


async def test_verbinden_ohne_bestehende_verbindung(hass: HomeAssistant) -> None:
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE"}, options={"tmdb_token": "x" * 50})
    eintrag.add_to_hass(hass)
    widerruf = AsyncMock(return_value=True)
    with (
        patch("custom_components.streaming_finder.async_setup_entry", return_value=True),
        patch.object(quellen, "freigabe_anfordern", AsyncMock(return_value="anfrage")),
        patch.object(quellen, "freigabe_abholen", AsyncMock(return_value=("neu-konto", "2"))),
        patch.object(quellen, "sitzung_aus_konto_token", AsyncMock(return_value=("neu-sitzung", 8))),
        patch.object(quellen, "zugang_widerrufen", widerruf),
    ):
        flow = await _bis_konto(hass, eintrag)
        ergebnis = await hass.config_entries.options.async_configure(flow, {})
    assert ergebnis["type"] is FlowResultType.CREATE_ENTRY
    assert eintrag.options[CONF_KONTO_SITZUNG] == "neu-sitzung"
    widerruf.assert_not_awaited()


async def test_inzwischen_verbunden_widerruft_neue_zugaenge(hass: HomeAssistant) -> None:
    """Wurde während des Dialogs anderswo verbunden, bleiben weder alte noch neue Zugänge verwaist."""
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE"}, options={"tmdb_token": "x" * 50})
    eintrag.add_to_hass(hass)
    widerruf = AsyncMock(return_value=True)
    with (
        patch("custom_components.streaming_finder.async_setup_entry", return_value=True),
        patch.object(quellen, "freigabe_anfordern", AsyncMock(return_value="anfrage")),
        patch.object(quellen, "freigabe_abholen", AsyncMock(return_value=("neu-konto", "2"))),
        patch.object(quellen, "sitzung_aus_konto_token", AsyncMock(return_value=("neu-sitzung", 8))),
        patch.object(quellen, "zugang_widerrufen", widerruf),
    ):
        flow = await _bis_konto(hass, eintrag)
        hass.config_entries.async_update_entry(eintrag, options=KONTO)
        ergebnis = await hass.config_entries.options.async_configure(flow, {})
    assert ergebnis["type"] is FlowResultType.ABORT and ergebnis["reason"] == "erst_trennen"
    widerruf.assert_awaited_once()
    assert widerruf.await_args.args[2:] == ("neu-sitzung", "neu-konto")
    assert eintrag.options == KONTO  # die bestehende Verbindung bleibt bekannt und widerrufbar
