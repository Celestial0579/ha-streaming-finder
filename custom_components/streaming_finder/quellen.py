"""Abfragen bei AniList (Anime-Season) und TMDB (Streaming-Angebote je Land)."""

from __future__ import annotations

from typing import Any

import aiohttp

USER_AGENT = "HomeAssistant-streaming_finder/0.1 (+https://github.com/Celestial0579/ha-streaming-finder)"
_ZEIT = aiohttp.ClientTimeout(total=20)

ANILIST_URL = "https://graphql.anilist.co"
ANILIST_ABFRAGE = """
query ($saison: MediaSeason, $jahr: Int, $anzahl: Int) {
  Page(perPage: $anzahl) {
    media(season: $saison, seasonYear: $jahr, type: ANIME, isAdult: false,
          format_in: [TV, TV_SHORT, ONA, MOVIE], sort: POPULARITY_DESC) {
      id
      title { romaji english native }
      format episodes status averageScore genres
      startDate { year month day }
      nextAiringEpisode { episode airingAt }
      externalLinks { site type }
      siteUrl
    }
  }
}
"""

TMDB_URL = "https://api.themoviedb.org/3"


class QuellenFehler(Exception):
    """Ein Dienst hat nicht wie erwartet geantwortet."""


async def anilist_saison(sitzung: aiohttp.ClientSession, saison: str, jahr: int, anzahl: int) -> list[dict[str, Any]]:
    try:
        async with sitzung.post(
            ANILIST_URL,
            json={"query": ANILIST_ABFRAGE, "variables": {"saison": saison, "jahr": jahr, "anzahl": anzahl}},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=_ZEIT,
        ) as antwort:
            if antwort.status == 429:
                raise QuellenFehler("AniList: zu viele Anfragen, bitte später erneut")
            if antwort.status != 200:
                raise QuellenFehler(f"AniList: HTTP {antwort.status}")
            daten = await antwort.json()
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise QuellenFehler(f"AniList nicht erreichbar: {err}") from err
    if daten.get("errors"):
        raise QuellenFehler(f"AniList: {daten['errors'][0].get('message')}")
    return daten["data"]["Page"]["media"]


def _tmdb_kopf(token: str) -> tuple[dict[str, str], dict[str, str]]:
    """Lesezugriffs-Token (lang) als Bearer, kurzer v3-Schlüssel als Parameter."""
    kopf = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if len(token) > 40:
        return {**kopf, "Authorization": f"Bearer {token}"}, {}
    return kopf, {"api_key": token}


async def tmdb(sitzung: aiohttp.ClientSession, token: str, pfad: str, parameter: dict[str, Any]) -> dict[str, Any]:
    kopf, schluessel = _tmdb_kopf(token)
    try:
        async with sitzung.get(
            f"{TMDB_URL}{pfad}", params={**parameter, **schluessel}, headers=kopf, timeout=_ZEIT
        ) as antwort:
            if antwort.status == 401:
                raise QuellenFehler("TMDB: Schlüssel ungültig")
            if antwort.status == 429:
                raise QuellenFehler("TMDB: zu viele Anfragen, bitte später erneut")
            if antwort.status != 200:
                raise QuellenFehler(f"TMDB: HTTP {antwort.status}")
            return await antwort.json()
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise QuellenFehler(f"TMDB nicht erreichbar: {err}") from err


def anbieter(ergebnis: dict[str, Any], land: str) -> dict[str, list[str]] | None:
    """Streaming-Angebote eines Titels im Land aus /watch/providers."""
    daten = (ergebnis.get("results") or {}).get(land)
    if not daten:
        return None
    namen = lambda schluessel: [a["provider_name"] for a in sorted(daten.get(schluessel) or [], key=lambda a: a.get("display_priority", 99))]
    return {
        "abo": namen("flatrate"),
        "kostenlos": namen("free"),
        "mit_werbung": namen("ads"),
        "leihen": namen("rent"),
        "kaufen": namen("buy"),
    }
