"""Einrichtung über die Oberfläche."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import quellen
from .const import CONF_LAND, CONF_SPRACHE, CONF_TMDB_TOKEN, DEFAULT_LAND, DEFAULT_SPRACHE, DOMAIN

PASSWORT = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


async def _pruefen(flow, token: str) -> str | None:
    if not token:
        return None
    try:
        await quellen.tmdb(async_get_clientsession(flow.hass), token, "/configuration", {})
    except quellen.QuellenFehler as err:
        return "tmdb_ungueltig" if "ungültig" in str(err) else "tmdb_nicht_erreichbar"
    return None


class StreamingFinderConfigFlow(ConfigFlow, domain=DOMAIN):
    """Land, Sprache und optional TMDB-Schlüssel."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fehler: dict[str, str] = {}
        if user_input is not None:
            land = str(user_input[CONF_LAND]).strip().upper()
            if len(land) != 2 or not land.isalpha():
                fehler[CONF_LAND] = "land_ungueltig"
            elif problem := await _pruefen(self, str(user_input.get(CONF_TMDB_TOKEN) or "").strip()):
                fehler[CONF_TMDB_TOKEN] = problem
            else:
                return self.async_create_entry(
                    title="Streaming-Finder",
                    data={**user_input, CONF_LAND: land, CONF_TMDB_TOKEN: str(user_input.get(CONF_TMDB_TOKEN) or "").strip()},
                )
        return self.async_show_form(
            step_id="user",
            errors=fehler,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LAND, default=DEFAULT_LAND): str,
                    vol.Required(CONF_SPRACHE, default=DEFAULT_SPRACHE): str,
                    vol.Optional(CONF_TMDB_TOKEN): PASSWORT,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return StreamingFinderOptionsFlow()


class StreamingFinderOptionsFlow(OptionsFlow):
    """TMDB-Schlüssel nachtragen oder ändern."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fehler: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input.get(CONF_TMDB_TOKEN) or "").strip()
            if problem := await _pruefen(self, token):
                fehler[CONF_TMDB_TOKEN] = problem
            else:
                return self.async_create_entry(data={CONF_TMDB_TOKEN: token})
        return self.async_show_form(
            step_id="init", errors=fehler, data_schema=vol.Schema({vol.Optional(CONF_TMDB_TOKEN): PASSWORT})
        )
