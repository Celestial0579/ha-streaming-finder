"""Beantwortet „Wo läuft …?“ und „Welche Animes laufen diese Season?“ – mit Zwischenspeicher."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from . import quellen
from .const import (
    CONF_LAND,
    CONF_SPRACHE,
    CONF_TMDB_TOKEN,
    DEFAULT_LAND,
    DEFAULT_SPRACHE,
    SAISON_DEUTSCH,
    SAISONS,
    STATUS_DEUTSCH,
)

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
STUNDE = 3600


class Finder:
    """Eine Instanz je Eintrag."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._speicher: dict[str, tuple[float, Any]] = {}
        self.merkliste = None

    @property
    def token(self) -> str:
        return str(self.entry.options.get(CONF_TMDB_TOKEN) or self.entry.data.get(CONF_TMDB_TOKEN) or "").strip()

    @property
    def land(self) -> str:
        return self.entry.data.get(CONF_LAND, DEFAULT_LAND)

    @property
    def sprache(self) -> str:
        return self.entry.data.get(CONF_SPRACHE, DEFAULT_SPRACHE)

    async def _gemerkt(self, schluessel: str, dauer: float, abruf) -> Any:
        jetzt = time.monotonic()
        eintrag = self._speicher.get(schluessel)
        if eintrag and jetzt - eintrag[0] < dauer:
            return eintrag[1]
        wert = await abruf()
        self._speicher[schluessel] = (jetzt, wert)
        if len(self._speicher) > 500:
            for alt in sorted(self._speicher, key=lambda k: self._speicher[k][0])[:100]:
                self._speicher.pop(alt, None)
        return wert

    async def _tmdb(self, pfad: str, parameter: dict[str, Any], dauer: float) -> dict[str, Any]:
        sitzung = async_get_clientsession(self.hass)
        schluessel = pfad + "|" + "&".join(f"{k}={v}" for k, v in sorted(parameter.items()))
        return await self._gemerkt(schluessel, dauer, lambda: quellen.tmdb(sitzung, self.token, pfad, parameter))

    async def angebote(self, art: str, tmdb_id: int) -> dict[str, list[str]] | None:
        daten = await self._tmdb(f"/{art}/{tmdb_id}/watch/providers", {}, 12 * STUNDE)
        return quellen.anbieter(daten, self.land)

    # ------------------------------------------------------------ Wo läuft …?
    async def async_wo_laeuft(self, titel: str, art: str, jahr: int | None) -> dict[str, Any]:
        if not self.token:
            raise ServiceValidationError("Für „Wo läuft …?“ fehlt der TMDB-Schlüssel (Integration › Konfigurieren).")
        pfad = {"serie": "/search/tv", "film": "/search/movie"}.get(art, "/search/multi")
        parameter: dict[str, Any] = {"query": titel, "language": self.sprache, "include_adult": "false"}
        if jahr and art == "film":
            parameter["year"] = jahr
        elif jahr and art == "serie":
            parameter["first_air_date_year"] = jahr
        try:
            suche = await self._tmdb(pfad, parameter, 12 * STUNDE)
            treffer = []
            for e in suche.get("results") or []:
                typ = e.get("media_type") or ("tv" if art == "serie" else "movie")
                if typ not in ("tv", "movie"):
                    continue
                datum = e.get("first_air_date") or e.get("release_date") or ""
                eintrag = {
                    "titel": e.get("name") or e.get("title"),
                    "originaltitel": e.get("original_name") or e.get("original_title"),
                    "art": "Serie" if typ == "tv" else "Film",
                    "jahr": datum[:4] or None,
                    "angebote": await self.angebote(typ, e["id"]),
                }
                if eintrag["angebote"] is None:
                    eintrag["hinweis"] = f"In {self.land} derzeit bei keinem Streamingdienst gelistet"
                treffer.append(eintrag)
                if len(treffer) >= 3:
                    break
        except quellen.QuellenFehler as err:
            raise HomeAssistantError(str(err)) from err
        return {"suche": titel, "land": self.land, "treffer": treffer, "quelle": "JustWatch über TMDB"}

    # ------------------------------------------------------------ Anime-Season
    def _saison(self, saison: str | None, jahr: int | None) -> tuple[str, int]:
        jetzt = dt_util.now()
        if saison:
            wert = SAISONS.get(saison.strip().lower(), saison.strip().upper())
            if wert not in SAISON_DEUTSCH:
                raise ServiceValidationError(f"Unbekannte Season: {saison} (Winter, Frühling, Sommer, Herbst)")
        else:
            wert = ["WINTER", "SPRING", "SUMMER", "FALL"][(jetzt.month - 1) // 3]
        return wert, int(jahr or jetzt.year)

    async def async_anime_saison(self, saison: str | None, jahr: int | None, anzahl: int) -> dict[str, Any]:
        wert, jahr = self._saison(saison, jahr)
        sitzung = async_get_clientsession(self.hass)
        try:
            liste = await self._gemerkt(
                f"anilist|{wert}|{jahr}|{anzahl}", 6 * STUNDE, lambda: quellen.anilist_saison(sitzung, wert, jahr, anzahl)
            )
        except quellen.QuellenFehler as err:
            raise HomeAssistantError(str(err)) from err
        ergebnis = []
        for m in liste:
            titel = m["title"].get("english") or m["title"].get("romaji")
            eintrag: dict[str, Any] = {
                "titel": titel,
                "titel_romaji": m["title"].get("romaji"),
                "format": m.get("format"),
                "folgen": m.get("episodes"),
                "status": STATUS_DEUTSCH.get(m.get("status"), m.get("status")),
                "genres": m.get("genres") or [],
                "bewertung": m.get("averageScore"),
                "plattformen_weltweit": sorted({l["site"] for l in m.get("externalLinks") or [] if l.get("type") == "STREAMING"}),
            }
            if folge := m.get("nextAiringEpisode"):
                zeit = dt_util.as_local(dt_util.utc_from_timestamp(folge["airingAt"]))
                eintrag["naechste_folge"] = {"nummer": folge["episode"], "termin": f"{WOCHENTAGE[zeit.weekday()]}, {zeit.strftime('%d.%m. %H:%M')}"}
            if self.token:
                eintrag["angebote_" + self.land.lower()] = await self._anime_angebote(m)
            ergebnis.append(eintrag)
        return {
            "season": f"{SAISON_DEUTSCH[wert]} {jahr}",
            "anzahl": len(ergebnis),
            "animes": ergebnis,
            "hinweis": None if self.token else f"Plattformen weltweit laut AniList; Verfügbarkeit in {self.land} kann abweichen",
        }

    async def _anime_angebote(self, m: dict[str, Any]) -> dict[str, list[str]] | None:
        jahr = (m.get("startDate") or {}).get("year")
        art = "movie" if m.get("format") == "MOVIE" else "tv"
        for name in (m["title"].get("english"), m["title"].get("romaji"), m["title"].get("native")):
            if not name:
                continue
            try:
                suche = await self._tmdb(f"/search/{art}", {"query": name, "language": self.sprache}, 24 * STUNDE)
            except quellen.QuellenFehler:
                return None
            for e in suche.get("results") or []:
                if 16 in (e.get("genre_ids") or []):  # Animation
                    try:
                        return await self.angebote(art, e["id"])
                    except quellen.QuellenFehler:
                        return None
        return None
