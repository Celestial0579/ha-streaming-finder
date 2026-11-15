"""Merkliste, Schlüssel, Anime-Season und Termine."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.streaming_finder import quellen
from custom_components.streaming_finder.const import CONF_KONTO_ID, CONF_KONTO_SITZUNG, CONF_KONTO_TOKEN, CONF_KONTO_V3, DOMAIN
from custom_components.streaming_finder.finder import Finder, lese_token
from custom_components.streaming_finder.merkliste import (
    MerklisteKoordinator,
    _haupttitel,
    angebot_text,
    passende_eintraege,
)

LISTE = [
    {"id": "movie-1", "titel": "Spirit - Der wilde Mustang"},
    {"id": "tv-2", "titel": "Cyberpunk: Edgerunners"},
    {"id": "tv-3", "titel": "The Boys"},
]


def test_passende_eintraege() -> None:
    assert passende_eintraege("the boys", LISTE) == [LISTE[2]]
    assert passende_eintraege("Spirit", LISTE) == [LISTE[0]]
    assert passende_eintraege("edgerunners", LISTE) == [LISTE[1]]
    assert passende_eintraege("The Boyz", LISTE) == [LISTE[2]]
    assert passende_eintraege("Dark", LISTE) == []
    assert passende_eintraege("  ", LISTE) == []


def test_haupttitel_und_angebot_text() -> None:
    assert _haupttitel("Spirit - Der wilde Mustang") == "Spirit"
    assert _haupttitel("Cyberpunk: Edgerunners") == "Cyberpunk"
    assert angebot_text(None) == "derzeit bei keinem Streamingdienst"
    assert angebot_text({"abo": ["Netflix"], "kostenlos": [], "mit_werbung": ["RTL+"]}) == "Abo: Netflix · mit Werbung: RTL+"
    assert angebot_text({"leihen": ["B", "A"], "kaufen": ["A"]}) == "nur leihen/kaufen: A, B"


def test_lese_token() -> None:
    ersteinrichtung = MockConfigEntry(domain=DOMAIN, data={"tmdb_token": "alt"})
    assert lese_token(ersteinrichtung) == "alt"
    geleert = MockConfigEntry(domain=DOMAIN, data={"tmdb_token": "alt"}, options={"tmdb_token": ""})
    assert lese_token(geleert) == ""  # leer heißt: ohne TMDB, nicht zurück zum alten Schlüssel
    neu = MockConfigEntry(domain=DOMAIN, data={"tmdb_token": "alt"}, options={"tmdb_token": " neu "})
    assert lese_token(neu) == "neu"


async def test_anime_fragt_nach_einem_fehler_nicht_weiter(hass: HomeAssistant) -> None:
    eintrag = MockConfigEntry(domain=DOMAIN, data={"land": "DE", "sprache": "de-DE", "tmdb_token": "x"})
    finder = Finder(hass, eintrag)
    animes = [{"title": {"english": f"Titel {n}"}, "format": "TV"} for n in range(20)]
    tmdb = AsyncMock(side_effect=quellen.QuellenFehler("TMDB: zu viele Anfragen"))
    with (
        patch.object(quellen, "anilist_saison", AsyncMock(return_value=animes)),
        patch.object(finder, "_tmdb", tmdb),
    ):
        antwort = await finder.async_anime_saison("Herbst", 2026, 20)
    assert antwort["anzahl"] == 20
    assert tmdb.await_count == 1
    assert "TMDB nicht erreichbar" in antwort["hinweis"]


async def test_entfernen_streicht_auch_die_termine(hass: HomeAssistant) -> None:
    eintrag = MockConfigEntry(
        domain=DOMAIN, data={"land": "DE"}, options={"tmdb_token": "x", CONF_KONTO_TOKEN: "k", CONF_KONTO_ID: "1", CONF_KONTO_SITZUNG: "s", CONF_KONTO_V3: 7}
    )
    eintrag.add_to_hass(hass)
    koordinator = MerklisteKoordinator(hass, eintrag, Finder(hass, eintrag))
    koordinator.async_set_updated_data([{"id": "tv-12", "titel": "A"}, {"id": "tv-123", "titel": "B"}])
    koordinator.termine = [
        {"uid": "tv-12-S01E01", "datum": date(2026, 11, 20)},
        {"uid": "tv-123-S01E01", "datum": date(2026, 11, 21)},
    ]
    with patch.object(quellen, "merkliste_setzen", AsyncMock()) as setzen:
        await koordinator.async_entfernen("tv-12")
    setzen.assert_awaited_once()
    assert [t["uid"] for t in koordinator.termine] == ["tv-123-S01E01"]
    assert [e["id"] for e in koordinator.data] == ["tv-123"]


async def test_gestoerte_merkliste_haelt_den_eintrag_nicht_auf(hass: HomeAssistant) -> None:
    eintrag = MockConfigEntry(
        domain=DOMAIN, data={"land": "DE", "sprache": "de-DE", "tmdb_token": "x"},
        options={"tmdb_token": "x", CONF_KONTO_TOKEN: "k", CONF_KONTO_ID: "1"},
    )
    eintrag.add_to_hass(hass)
    with patch.object(quellen, "merkliste", AsyncMock(side_effect=quellen.QuellenFehler("TMDB: Zugriff verweigert"))):
        assert await hass.config_entries.async_setup(eintrag.entry_id)
        await hass.async_block_till_done()
    assert eintrag.state is ConfigEntryState.LOADED
    zustaende = {s.entity_id: s.state for s in hass.states.async_all("todo")}
    assert list(zustaende.values()) == ["unavailable"], zustaende
    assert hass.services.has_service(DOMAIN, "anime_saison")
