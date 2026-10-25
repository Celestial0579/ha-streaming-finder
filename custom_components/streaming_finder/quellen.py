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
TMDB4_URL = "https://api.themoviedb.org/4"
TMDB_FREIGABE = "https://www.themoviedb.org/auth/access?request_token={}"


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


async def tmdb4(
    sitzung: aiohttp.ClientSession, token: str, methode: str, pfad: str,
    inhalt: dict[str, Any] | None = None, parameter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aufruf der TMDB-API v4 (Konto); token ist der Lese- oder der Konto-Token."""
    kopf = {"User-Agent": USER_AGENT, "Accept": "application/json", "Authorization": f"Bearer {token}"}
    try:
        async with sitzung.request(
            methode, f"{TMDB4_URL}{pfad}", json=inhalt, params=parameter or {}, headers=kopf, timeout=_ZEIT
        ) as antwort:
            daten = await antwort.json(content_type=None)
            if antwort.status == 401:
                raise QuellenFehler("TMDB: Zugriff verweigert" + (f" ({daten.get('status_message')})" if isinstance(daten, dict) else ""))
            if antwort.status == 429:
                raise QuellenFehler("TMDB: zu viele Anfragen, bitte später erneut")
            if antwort.status >= 400:
                raise QuellenFehler(f"TMDB: HTTP {antwort.status}")
            return daten
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise QuellenFehler(f"TMDB nicht erreichbar: {err}") from err


async def freigabe_anfordern(sitzung: aiohttp.ClientSession, lese_token: str) -> str:
    """Anfrage-Token, den der Nutzer bei TMDB genehmigt."""
    daten = await tmdb4(sitzung, lese_token, "POST", "/auth/request_token", {})
    if not daten.get("request_token"):
        raise QuellenFehler("TMDB: kein Anfrage-Token erhalten")
    return daten["request_token"]


async def freigabe_abholen(sitzung: aiohttp.ClientSession, lese_token: str, anfrage: str) -> tuple[str, str]:
    """Nach der Genehmigung: Konto-Token und Konto-Kennung."""
    daten = await tmdb4(sitzung, lese_token, "POST", "/auth/access_token", {"request_token": anfrage})
    if not daten.get("access_token") or not daten.get("account_id"):
        raise QuellenFehler("TMDB: Freigabe noch nicht erteilt")
    return daten["access_token"], str(daten["account_id"])


async def merkliste(
    sitzung: aiohttp.ClientSession, konto_token: str, konto_id: str, art: str, sprache: str, max_seiten: int
) -> list[dict[str, Any]]:
    """Alle Einträge der Merkliste einer Art („tv“ oder „movie“)."""
    eintraege: list[dict[str, Any]] = []
    seite = 1
    while seite <= max_seiten:
        daten = await tmdb4(
            sitzung, konto_token, "GET", f"/account/{konto_id}/{art}/watchlist",
            parameter={"page": seite, "language": sprache, "sort_by": "created_at.desc"},
        )
        eintraege.extend(daten.get("results") or [])
        if seite >= int(daten.get("total_pages") or 1):
            break
        seite += 1
    return eintraege


async def tmdb_schreiben(
    sitzung: aiohttp.ClientSession, lese_token: str, pfad: str, inhalt: dict[str, Any], parameter: dict[str, Any] | None = None
) -> dict[str, Any]:
    """POST an die TMDB-API v3."""
    kopf, schluessel = _tmdb_kopf(lese_token)
    try:
        async with sitzung.post(
            f"{TMDB_URL}{pfad}", json=inhalt, params={**(parameter or {}), **schluessel}, headers=kopf, timeout=_ZEIT
        ) as antwort:
            daten = await antwort.json(content_type=None)
            if antwort.status >= 400:
                text = daten.get("status_message") if isinstance(daten, dict) else None
                raise QuellenFehler(f"TMDB: HTTP {antwort.status}" + (f" ({text})" if text else ""))
            return daten
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise QuellenFehler(f"TMDB nicht erreichbar: {err}") from err


async def sitzung_aus_konto_token(sitzung: aiohttp.ClientSession, lese_token: str, konto_token: str) -> tuple[str, int]:
    """Aus dem Konto-Token (v4) eine v3-Sitzung und die v3-Kontonummer ableiten – nötig zum Ändern der Merkliste."""
    daten = await tmdb_schreiben(sitzung, lese_token, "/authentication/session/convert/4", {"access_token": konto_token})
    sitzungs_id = daten.get("session_id")
    if not sitzungs_id:
        raise QuellenFehler("TMDB: keine Sitzung erhalten")
    konto = await tmdb(sitzung, lese_token, "/account", {"session_id": sitzungs_id})
    return sitzungs_id, int(konto["id"])


async def merkliste_setzen(
    sitzung: aiohttp.ClientSession, lese_token: str, konto_v3: int, sitzungs_id: str, art: str, tmdb_id: int, merken: bool
) -> None:
    await tmdb_schreiben(
        sitzung, lese_token, f"/account/{konto_v3}/watchlist",
        {"media_type": art, "media_id": tmdb_id, "watchlist": merken}, {"session_id": sitzungs_id},
    )


def bester_treffer(text: str, ergebnisse: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ergebnisse mit genau passendem Titel (deutsch oder Original) zuerst, darunter die bekanntesten."""
    gesucht = text.strip().casefold()

    def namen(e: dict[str, Any]) -> set[str]:
        return {str(e.get(k) or "").casefold() for k in ("name", "title", "original_name", "original_title")} - {""}

    exakt = sorted((e for e in ergebnisse if gesucht in namen(e)), key=lambda e: -(e.get("vote_count") or 0))
    return exakt + [e for e in ergebnisse if gesucht not in namen(e)]


async def auf_merkliste(
    sitzung: aiohttp.ClientSession, lese_token: str, sitzungs_id: str, art: str, tmdb_id: int
) -> bool:
    """Steht der Titel laut TMDB schon auf der Merkliste?"""
    daten = await tmdb(sitzung, lese_token, f"/{art}/{tmdb_id}/account_states", {"session_id": sitzungs_id})
    return bool(daten.get("watchlist"))
