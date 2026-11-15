"""GHSA-f7x2-p725-fc44: Schlüssel bei verbundenem Konto nicht ändern; ohne Schlüssel kein Schein-Widerruf (Attrappen)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.streaming_finder import quellen
from custom_components.streaming_finder.const import CONF_KONTO_ID, CONF_KONTO_SITZUNG, CONF_KONTO_TOKEN, CONF_KONTO_V3, DOMAIN

ALT = "a" * 50
KONTO = {"tmdb_token": ALT, CONF_KONTO_TOKEN: "konto", CONF_KONTO_ID: "1", CONF_KONTO_SITZUNG: "sitzung", CONF_KONTO_V3: 7}


async def _schluessel(hass: HomeAssistant, eintrag: MockConfigEntry, token: str) -> dict:
    ergebnis = await hass.config_entries.options.async_init(eintrag.entry_id)
    ergebnis = await hass.config_entries.options.async_configure(ergebnis["flow_id"], {"next_step_id": "schluessel"})
    return await hass.config_entries.options.async_configure(ergebnis["flow_id"], {"tmdb_token": token})


async def test_schluessel_bei_verbindung_nicht_aenderbar(hass: HomeAssistant) -> None:
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE"}, options=KONTO)
    eintrag.add_to_hass(hass)
    pruefen = AsyncMock(return_value=None)
    with (
        patch("custom_components.streaming_finder.async_setup_entry", return_value=True),
        patch("custom_components.streaming_finder.config_flow._pruefen", pruefen),
    ):
        for neu in ("", "b" * 50):
            ergebnis = await _schluessel(hass, eintrag, neu)
            assert ergebnis["type"] is FlowResultType.FORM
            assert ergebnis["errors"] == {"tmdb_token": "schluessel_verbunden"}
        ergebnis = await _schluessel(hass, eintrag, ALT)  # derselbe Schlüssel bleibt erlaubt
    assert ergebnis["type"] is FlowResultType.CREATE_ENTRY
    assert eintrag.options["tmdb_token"] == ALT


async def test_schluessel_ohne_verbindung_aenderbar(hass: HomeAssistant) -> None:
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE"}, options={"tmdb_token": ALT})
    eintrag.add_to_hass(hass)
    with (
        patch("custom_components.streaming_finder.async_setup_entry", return_value=True),
        patch("custom_components.streaming_finder.config_flow._pruefen", AsyncMock(return_value=None)),
    ):
        ergebnis = await _schluessel(hass, eintrag, "")
    assert ergebnis["type"] is FlowResultType.CREATE_ENTRY and eintrag.options["tmdb_token"] == ""


async def test_widerruf_ohne_schluessel_meldet_fehlschlag(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    sitzung = async_get_clientsession(hass)
    assert not await quellen.zugang_widerrufen(sitzung, "", "sitzung", "konto")
    assert aioclient_mock.call_count == 0  # kein Aufruf mit leerem Schlüssel
    assert await quellen.zugang_widerrufen(sitzung, "", None, None)


async def test_trennen_ohne_schluessel_sagt_es(hass: HomeAssistant) -> None:
    """Alte Einträge, deren Schlüssel schon geleert wurde: Trennen meldet den gescheiterten Widerruf."""
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE"}, options={**KONTO, "tmdb_token": ""})
    eintrag.add_to_hass(hass)
    with patch("custom_components.streaming_finder.async_setup_entry", return_value=True):
        ergebnis = await hass.config_entries.options.async_init(eintrag.entry_id)
        ergebnis = await hass.config_entries.options.async_configure(ergebnis["flow_id"], {"next_step_id": "trennen"})
        ergebnis = await hass.config_entries.options.async_configure(ergebnis["flow_id"], {})
    assert ergebnis["errors"] == {"base": "widerruf_gescheitert"}
