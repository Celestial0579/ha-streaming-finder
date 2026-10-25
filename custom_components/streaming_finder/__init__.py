"""Streaming-Finder: Wo läuft eine Serie oder ein Film, und welche Animes laufen diese Season."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_KONTO_TOKEN, DIENST_ANIME_SAISON, DIENST_MERKLISTE, DIENST_WO_LAEUFT, DOMAIN
from .finder import Finder
from .merkliste import MerklisteKoordinator

PLATFORMS = [Platform.CALENDAR, Platform.TODO]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type StreamingFinderConfigEntry = ConfigEntry[Finder]

WO_SCHEMA = vol.Schema(
    {
        vol.Required("titel"): cv.string,
        vol.Optional("art", default="egal"): vol.In(["serie", "film", "egal"]),
        vol.Optional("jahr"): vol.Coerce(int),
    }
)
ANIME_SCHEMA = vol.Schema(
    {
        vol.Optional("saison"): cv.string,
        vol.Optional("jahr"): vol.Coerce(int),
        vol.Optional("anzahl", default=15): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
    }
)


def _finder(hass: HomeAssistant) -> Finder:
    eintraege = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
    if not eintraege:
        raise ServiceValidationError("Streaming-Finder ist nicht eingerichtet.")
    return eintraege[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def wo_laeuft(aufruf: ServiceCall) -> ServiceResponse:
        return await _finder(hass).async_wo_laeuft(aufruf.data["titel"], aufruf.data["art"], aufruf.data.get("jahr"))

    async def anime_saison(aufruf: ServiceCall) -> ServiceResponse:
        return await _finder(hass).async_anime_saison(aufruf.data.get("saison"), aufruf.data.get("jahr"), aufruf.data["anzahl"])

    hass.services.async_register(DOMAIN, DIENST_WO_LAEUFT, wo_laeuft, schema=WO_SCHEMA, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, DIENST_ANIME_SAISON, anime_saison, schema=ANIME_SCHEMA, supports_response=SupportsResponse.ONLY)

    async def merkliste(aufruf: ServiceCall) -> ServiceResponse:
        finder = _finder(hass)
        if finder.merkliste is None:
            raise ServiceValidationError("Kein TMDB-Konto verbunden (Streaming-Finder › Konfigurieren › TMDB-Konto verbinden).")
        if aufruf.data.get("aktualisieren"):
            await finder.merkliste.async_refresh()
        eintraege = finder.merkliste.data or []
        return {"anzahl": len(eintraege), "eintraege": [{k: v for k, v in e.items() if k != "id"} for e in eintraege], "land": finder.land}

    hass.services.async_register(
        DOMAIN, DIENST_MERKLISTE, merkliste, schema=vol.Schema({vol.Optional("aktualisieren", default=False): cv.boolean}),
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: StreamingFinderConfigEntry) -> bool:
    finder = Finder(hass, entry)
    if entry.options.get(CONF_KONTO_TOKEN):
        finder.merkliste = MerklisteKoordinator(hass, entry, finder)
        await finder.merkliste.async_config_entry_first_refresh()
    entry.runtime_data = finder
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_optionen_geaendert))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StreamingFinderConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _optionen_geaendert(hass: HomeAssistant, entry: StreamingFinderConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
