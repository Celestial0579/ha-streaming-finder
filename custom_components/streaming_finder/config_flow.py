"""Einrichtung über die Oberfläche."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import quellen
from .const import (
    CONF_KONTO_ID,
    CONF_KONTO_SITZUNG,
    CONF_KONTO_TOKEN,
    CONF_KONTO_V3,
    CONF_LAND,
    CONF_SPRACHE,
    CONF_TMDB_TOKEN,
    DEFAULT_LAND,
    DEFAULT_SPRACHE,
    DOMAIN,
)

PASSWORT = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))
KONTO_SCHLUESSEL = (CONF_KONTO_TOKEN, CONF_KONTO_ID, CONF_KONTO_SITZUNG, CONF_KONTO_V3)


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
    """Schlüssel ändern, TMDB-Konto verbinden oder trennen."""

    def __init__(self) -> None:
        self._anfrage: str | None = None

    def _lese_token(self) -> str:
        return str(self.config_entry.options.get(CONF_TMDB_TOKEN) or self.config_entry.data.get(CONF_TMDB_TOKEN) or "")

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        punkte = ["schluessel", "konto"]
        if self.config_entry.options.get(CONF_KONTO_TOKEN):
            punkte.append("trennen")
        return self.async_show_menu(step_id="init", menu_options=punkte)

    async def async_step_schluessel(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fehler: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input.get(CONF_TMDB_TOKEN) or "").strip()
            if problem := await _pruefen(self, token):
                fehler[CONF_TMDB_TOKEN] = problem
            else:
                return self.async_create_entry(data={**self.config_entry.options, CONF_TMDB_TOKEN: token})
        return self.async_show_form(
            step_id="schluessel", errors=fehler, data_schema=vol.Schema({vol.Optional(CONF_TMDB_TOKEN): PASSWORT})
        )

    async def async_step_konto(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        lese = self._lese_token()
        if not lese:
            return self.async_abort(reason="erst_schluessel")
        sitzung = async_get_clientsession(self.hass)
        fehler: dict[str, str] = {}
        if user_input is not None and self._anfrage:
            try:
                konto_token, konto_id = await quellen.freigabe_abholen(sitzung, lese, self._anfrage)
                sitzungs_id, konto_v3 = await quellen.sitzung_aus_konto_token(sitzung, lese, konto_token)
            except quellen.QuellenFehler:
                fehler["base"] = "nicht_freigegeben"
            else:
                return self.async_create_entry(
                    data={
                        **self.config_entry.options,
                        CONF_KONTO_TOKEN: konto_token,
                        CONF_KONTO_ID: konto_id,
                        CONF_KONTO_SITZUNG: sitzungs_id,
                        CONF_KONTO_V3: konto_v3,
                    }
                )
        if self._anfrage is None:
            try:
                self._anfrage = await quellen.freigabe_anfordern(sitzung, lese)
            except quellen.QuellenFehler:
                return self.async_abort(reason="tmdb_nicht_erreichbar")
        return self.async_show_form(
            step_id="konto",
            errors=fehler,
            data_schema=vol.Schema({}),
            description_placeholders={"link": quellen.TMDB_FREIGABE.format(self._anfrage)},
        )

    async def async_step_trennen(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={k: v for k, v in self.config_entry.options.items() if k not in KONTO_SCHLUESSEL}
            )
        return self.async_show_form(step_id="trennen", data_schema=vol.Schema({}))
