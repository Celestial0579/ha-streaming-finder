"""Hält die TMDB-Merkliste samt Streaming-Angeboten aktuell."""

from __future__ import annotations

from datetime import timedelta
import difflib
import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import quellen
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.intent import IntentHandleError

from datetime import date

from homeassistant.util import dt as dt_util

from .const import (
    CONF_KONTO_ID,
    CONF_KONTO_SITZUNG,
    CONF_KONTO_TOKEN,
    CONF_KONTO_V3,
    DOMAIN,
    FILM_ARTEN,
    MERKLISTE_MAX_SEITEN,
    MERKLISTE_STUNDEN,
    TERMINE_TAGE_ZURUECK,
)
from .finder import Finder

_LOGGER = logging.getLogger(__name__)


def _datum(text: str | None) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10]) if text else None
    except ValueError:
        return None


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


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", str(text).casefold()).split())


def _haupttitel(titel: str) -> str:
    """„Spirit - Der wilde Mustang“ → „Spirit“, „Cyberpunk: Edgerunners“ → „Cyberpunk“."""
    return re.split(r"\s[-–—]\s|:\s", str(titel), maxsplit=1)[0]


def passende_eintraege(text: str, eintraege: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Einträge zum gesprochenen Titel: erst genau, dann Haupttitel, dann alle Wörter, dann ungefähr."""
    gesucht = _norm(text)
    if not gesucht:
        return []

    def aehnlich(e: dict[str, Any]) -> bool:
        return max(difflib.SequenceMatcher(None, gesucht, _norm(n)).ratio() for n in (e["titel"], _haupttitel(e["titel"]))) >= 0.8

    stufen = (
        lambda e: _norm(e["titel"]) == gesucht,
        lambda e: _norm(_haupttitel(e["titel"])) == gesucht,
        lambda e: set(gesucht.split()) <= set(_norm(e["titel"]).split()),
        aehnlich,
    )
    for passt in stufen:
        treffer = [e for e in eintraege if passt(e)]
        if treffer:
            return treffer
    return []


class MerklisteKoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Lädt die Merkliste alle paar Stunden."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, finder: Finder) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_merkliste",
            update_interval=timedelta(hours=MERKLISTE_STUNDEN),
        )
        self.finder = finder
        self.termine: list[dict[str, Any]] = []

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
        if self.finder.token:
            try:
                self.termine = await self._termine(ergebnis)
            except quellen.QuellenFehler as err:
                _LOGGER.warning("Termine der Merkliste nicht geladen: %s", err)
        return ergebnis

    async def _termine(self, liste: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Anstehende Folgen (Serien) und Starttermine im Land (Filme)."""
        heute = dt_util.now().date()
        ab = heute.toordinal() - TERMINE_TAGE_ZURUECK
        termine: list[dict[str, Any]] = []
        for e in liste:
            art, _, kennung = e["id"].partition("-")
            wo = e["wo"]
            if art == "tv":
                serie = await self.finder.tmdb_lesen(f"/tv/{kennung}", 12)
                naechste = serie.get("next_episode_to_air") or {}
                folgen: list[dict[str, Any]] = []
                if naechste.get("season_number") is not None:
                    staffel = await self.finder.tmdb_lesen(f"/tv/{kennung}/season/{naechste['season_number']}", 12)
                    folgen = staffel.get("episodes") or []
                elif serie.get("last_episode_to_air"):
                    folgen = [serie["last_episode_to_air"]]
                for f in folgen:
                    datum = _datum(f.get("air_date"))
                    if datum and datum.toordinal() >= ab:
                        nummer = f"S{int(f.get('season_number') or 0):02d}E{int(f.get('episode_number') or 0):02d}"
                        name = f" „{f['name']}“" if f.get("name") and not str(f["name"]).lower().startswith(("episode", "folge")) else ""
                        termine.append({"uid": f"tv-{kennung}-{nummer}", "datum": datum, "titel": f"{e['titel']} – {nummer}{name}", "beschreibung": f"Neue Folge · {wo}"})
            else:
                daten = await self.finder.tmdb_lesen(f"/movie/{kennung}/release_dates", 24)
                land = next((r for r in daten.get("results") or [] if r.get("iso_3166_1") == self.finder.land), None)
                gesehen: set[tuple[date, str]] = set()
                for r in (land or {}).get("release_dates") or []:
                    datum = _datum(r.get("release_date"))
                    was = FILM_ARTEN.get(r.get("type"))
                    if datum and was and datum.toordinal() >= ab and (datum, was) not in gesehen:
                        gesehen.add((datum, was))
                        termine.append({"uid": f"movie-{kennung}-{r.get('type')}-{datum}", "datum": datum, "titel": f"{e['titel']} – {was}", "beschreibung": f"Film · {wo}"})
        return sorted(termine, key=lambda t: (t["datum"], t["titel"]))

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

    async def async_entfernen_titel(self, text: str) -> str:
        """Nimmt einen Titel von der Merkliste, auch verkürzt, leicht verhört oder im Original genannt."""
        eintraege = self.data or []
        treffer = passende_eintraege(text, eintraege) or await self._per_suche(text, eintraege)
        if not treffer:
            namen = ", ".join(f"„{e['titel']}“" for e in eintraege[:15]) or "nichts"
            raise IntentHandleError(f"„{text}“ steht nicht auf deiner Merkliste. Darauf stehen: {namen}.")
        if len(treffer) > 1:
            namen = ", ".join(f"„{e['titel']}“" for e in treffer)
            raise IntentHandleError(f"Zu „{text}“ passen mehrere Einträge: {namen}. Welchen meinst du?")
        await self.async_entfernen(treffer[0]["id"])
        return str(treffer[0]["titel"])

    async def _per_suche(self, text: str, eintraege: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Englisch oder im Original genannt: bei TMDB suchen und den besten Treffer auf der Liste nehmen."""
        if not self.finder.token or not eintraege:
            return []
        try:
            suche = await quellen.tmdb(
                async_get_clientsession(self.hass), self.finder.token, "/search/multi",
                {"query": text, "language": self.finder.sprache, "include_adult": "false"},
            )
        except quellen.QuellenFehler:
            return []
        kandidaten = [e for e in suche.get("results") or [] if e.get("media_type") in ("tv", "movie")]
        nach_id = {e["id"]: e for e in eintraege}
        for k in quellen.bester_treffer(text, kandidaten):
            if (e := nach_id.get(f"{k['media_type']}-{k['id']}")) is not None:
                return [e]
        return []

    async def async_hinzufuegen(self, text: str) -> str:
        try:
            suche = await quellen.tmdb(
                async_get_clientsession(self.hass), self.finder.token, "/search/multi",
                {"query": text, "language": self.finder.sprache, "include_adult": "false"},
            )
        except quellen.QuellenFehler as err:
            raise HomeAssistantError(str(err)) from err
        kandidaten = [e for e in suche.get("results") or [] if e.get("media_type") in ("tv", "movie")]
        treffer = (quellen.bester_treffer(text, kandidaten) or [None])[0]
        if treffer is None:
            # IntentHandleError statt HomeAssistantError: nur so erreicht der Text auch den Sprachassistenten
            raise IntentHandleError(f"Bei TMDB nichts zu „{text}“ gefunden.")
        name = str(treffer.get("name") or treffer.get("title"))
        schon_da = any(e["id"] == f"{treffer['media_type']}-{treffer['id']}" for e in self.data or [])
        if not schon_da and self.config_entry.options.get(CONF_KONTO_SITZUNG):
            try:
                schon_da = await quellen.auf_merkliste(
                    async_get_clientsession(self.hass), self.finder.token, self.config_entry.options[CONF_KONTO_SITZUNG],
                    treffer["media_type"], treffer["id"],
                )
            except quellen.QuellenFehler:
                schon_da = False
        if schon_da:
            raise IntentHandleError(f"„{name}“ steht schon auf deiner Merkliste.")
        await self._setzen(treffer["media_type"], treffer["id"], True)
        await self.async_request_refresh()
        return str(treffer.get("name") or treffer.get("title"))
