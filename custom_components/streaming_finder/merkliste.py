"""Hält die TMDB-Merkliste samt Streaming-Angeboten aktuell."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import quellen
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_KONTO_ID, CONF_KONTO_SITZUNG, CONF_KONTO_TOKEN, CONF_KONTO_V3, DOMAIN, MERKLISTE_MAX_SEITEN, MERKLISTE_STUNDEN
from .finder import Finder

_LOGGER = logging.getLogger(__name__)


def angebot_text(angebote: dict[str, list[str]] | None) -> str:
    if not angebote:
        return "derzeit bei keinem Streamingdienst"
    teile = []
    if angebote.get("abo"):
        teile.append("Abo: " + ", ".join(angebote["abo"]))
    if angebote.get("kostenlos"):
        teile.append("kostenlos: " + ", ".join(angebote["kostenlos"]))
    if angebote.get("mit_werbung"):
        teile.append("mit Werbung: " + ", ".join(angebote["mit_werbung"]))
    if not teile and (angebote.get("leihen") or angebote.get("kaufen")):
        teile.append("nur leihen/kaufen: " + ", ".join(sorted(set((angebote.get("leihen") or []) + (angebote.get("kaufen") or [])))[:4]))
    return " · ".join(teile) or "derzeit bei keinem Streamingdienst"


class MerklisteKoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Lädt die Merkliste alle paar Stunden."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, finder: Finder) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_merkliste",
            update_interval=timedelta(hours=MERKLISTE_STUNDEN),
        )
        self.finder = finder

    async def _async_update_data(self) -> list[dict[str, Any]]:
        optionen = self.config_entry.options
        sitzung = async_get_clientsession(self.hass)
        ergebnis: list[dict[str, Any]] = []
        try:
            for art in ("tv", "movie"):
                for e in await quellen.merkliste(
                    sitzung, optionen[CONF_KONTO_TOKEN], optionen[CONF_KONTO_ID], art,
                    self.finder.sprache, MERKLISTE_MAX_SEITEN,
                ):
                    datum = e.get("first_air_date") or e.get("release_date") or ""
                    angebote = await self.finder.angebote(art, e["id"]) if self.finder.token else None
                    ergebnis.append(
                        {
                            "id": f"{art}-{e['id']}",
                            "titel": e.get("name") or e.get("title"),
                            "art": "Serie" if art == "tv" else "Film",
                            "jahr": datum[:4] or None,
                            "angebote": angebote,
                            "wo": angebot_text(angebote),
                        }
                    )
        except quellen.QuellenFehler as err:
            raise UpdateFailed(str(err)) from err
        return ergebnis

    # ------------------------------------------------------------ Ändern
    async def _setzen(self, art: str, tmdb_id: int, merken: bool) -> None:
        optionen = self.config_entry.options
        if not optionen.get(CONF_KONTO_SITZUNG) or not optionen.get(CONF_KONTO_V3):
            raise HomeAssistantError("Ändern nicht freigegeben – bitte das TMDB-Konto neu verbinden (Konfigurieren).")
        try:
            await quellen.merkliste_setzen(
                async_get_clientsession(self.hass), self.finder.token, int(optionen[CONF_KONTO_V3]),
                optionen[CONF_KONTO_SITZUNG], art, tmdb_id, merken,
            )
        except quellen.QuellenFehler as err:
            raise HomeAssistantError(str(err)) from err

    async def async_entfernen(self, uid: str) -> None:
        art, _, kennung = uid.partition("-")
        await self._setzen(art, int(kennung), False)
        self.async_set_updated_data([e for e in self.data or [] if e["id"] != uid])

    async def async_hinzufuegen(self, text: str) -> str:
        try:
            suche = await quellen.tmdb(
                async_get_clientsession(self.hass), self.finder.token, "/search/multi",
                {"query": text, "language": self.finder.sprache, "include_adult": "false"},
            )
        except quellen.QuellenFehler as err:
            raise HomeAssistantError(str(err)) from err
        treffer = next((e for e in suche.get("results") or [] if e.get("media_type") in ("tv", "movie")), None)
        if treffer is None:
            raise HomeAssistantError(f"Bei TMDB nichts zu „{text}“ gefunden.")
        await self._setzen(treffer["media_type"], treffer["id"], True)
        await self.async_request_refresh()
        return str(treffer.get("name") or treffer.get("title"))
