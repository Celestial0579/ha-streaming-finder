"""Abrufe und Auswertung ohne TMDB und AniList (lokaler Nachbau)."""

from __future__ import annotations

from aiohttp import web
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.streaming_finder import quellen

SCHLUESSEL = "KURZER-V3-SCHLUESSEL"
SITZUNG = "GEHEIME-SITZUNG-123"


@pytest.fixture
async def nachbau(aiohttp_server, monkeypatch: pytest.MonkeyPatch):
    async def html(_request: web.Request) -> web.Response:
        return web.Response(text="<html>Wartung</html>", content_type="text/html")

    async def schleife(request: web.Request) -> web.Response:
        raise web.HTTPFound(location=str(request.rel_url))

    async def liste(_request: web.Request) -> web.Response:
        return web.json_response([1, 2])

    async def anilist_leer(_request: web.Request) -> web.Response:
        return web.json_response({"data": None})

    app = web.Application()
    app.router.add_get("/3/account", html)
    app.router.add_get("/3/search/multi", schleife)
    app.router.add_get("/3/liste", liste)
    app.router.add_post("/anilist", anilist_leer)
    server = await aiohttp_server(app)
    monkeypatch.setattr(quellen, "TMDB_URL", f"http://127.0.0.1:{server.port}/3")
    monkeypatch.setattr(quellen, "ANILIST_URL", f"http://127.0.0.1:{server.port}/anilist")
    return server


@pytest.mark.usefixtures("socket_enabled")
@pytest.mark.parametrize(("pfad", "parameter"), [("/account", {"session_id": SITZUNG}), ("/search/multi", {"query": "x"})])
async def test_fehlermeldung_ohne_schluessel_und_sitzung(hass: HomeAssistant, nachbau, pfad, parameter) -> None:
    with pytest.raises(quellen.QuellenFehler) as fehler:
        await quellen.tmdb(async_get_clientsession(hass), SCHLUESSEL, pfad, parameter)
    assert SCHLUESSEL not in str(fehler.value)
    assert SITZUNG not in str(fehler.value)
    assert "127.0.0.1" not in str(fehler.value)


@pytest.mark.usefixtures("socket_enabled")
async def test_antwort_ist_kein_objekt(hass: HomeAssistant, nachbau) -> None:
    with pytest.raises(quellen.QuellenFehler, match="unerwartete Antwort"):
        await quellen.tmdb(async_get_clientsession(hass), SCHLUESSEL, "/liste", {})


@pytest.mark.usefixtures("socket_enabled")
async def test_anilist_ohne_daten(hass: HomeAssistant, nachbau) -> None:
    with pytest.raises(quellen.QuellenFehler, match="AniList: unerwartete Antwort"):
        await quellen.anilist_saison(async_get_clientsession(hass), "FALL", 2026, 5)


def test_schluessel_im_kopf_oder_als_parameter() -> None:
    lang = "x" * 50
    kopf, parameter = quellen._tmdb_kopf(lang)
    assert kopf["Authorization"] == f"Bearer {lang}" and parameter == {}
    kopf, parameter = quellen._tmdb_kopf("kurz")
    assert "Authorization" not in kopf and parameter == {"api_key": "kurz"}


def test_anbieter() -> None:
    ergebnis = {
        "results": {
            "DE": {
                "flatrate": [
                    {"provider_name": "B", "display_priority": 5},
                    {"provider_name": "A", "display_priority": 1},
                    {"provider_name": "C", "display_priority": None},
                    "kaputt",
                ],
                "rent": [{"provider_name": "Leih"}],
            }
        }
    }
    angebote = quellen.anbieter(ergebnis, "DE")
    assert angebote["abo"] == ["A", "B", "C"]
    assert angebote["leihen"] == ["Leih"]
    assert quellen.anbieter(ergebnis, "AT") is None
    assert quellen.anbieter({"results": []}, "DE") is None


def test_bester_treffer() -> None:
    ergebnisse = [
        {"name": "The Boys Presents", "vote_count": 900},
        {"name": "The Boys", "vote_count": 10},
        {"original_title": "the boys", "vote_count": 50},
    ]
    treffer = quellen.bester_treffer(" The Boys ", ergebnisse)
    assert [e.get("vote_count") for e in treffer] == [50, 10, 900]


def test_user_agent_nennt_die_fassung() -> None:
    assert f"/{quellen.FASSUNG} " in quellen.USER_AGENT
