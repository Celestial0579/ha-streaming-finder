"""Konstanten für den Streaming-Finder."""

DOMAIN = "streaming_finder"

CONF_TMDB_TOKEN = "tmdb_token"
CONF_LAND = "land"
CONF_SPRACHE = "sprache"
CONF_KONTO_TOKEN = "konto_token"
CONF_KONTO_ID = "konto_id"
CONF_KONTO_SITZUNG = "konto_sitzung"
CONF_KONTO_V3 = "konto_v3"

DEFAULT_LAND = "DE"
DEFAULT_SPRACHE = "de-DE"

DIENST_WO_LAEUFT = "wo_laeuft"
DIENST_ANIME_SAISON = "anime_saison"
DIENST_MERKLISTE = "merkliste"
DIENST_MERKLISTE_ENTFERNEN = "merkliste_entfernen"

MERKLISTE_STUNDEN = 6
TERMINE_TAGE_ZURUECK = 14
FILM_ARTEN = {3: "Kinostart", 4: "Digital", 5: "DVD/Blu-ray", 6: "im Fernsehen"}
MERKLISTE_MAX_SEITEN = 10

SAISONS = {
    "winter": "WINTER", "frühling": "SPRING", "fruehling": "SPRING", "spring": "SPRING",
    "sommer": "SUMMER", "summer": "SUMMER", "herbst": "FALL", "fall": "FALL", "autumn": "FALL",
}
SAISON_DEUTSCH = {"WINTER": "Winter", "SPRING": "Frühling", "SUMMER": "Sommer", "FALL": "Herbst"}
STATUS_DEUTSCH = {
    "RELEASING": "läuft", "FINISHED": "abgeschlossen", "NOT_YET_RELEASED": "noch nicht gestartet",
    "CANCELLED": "abgebrochen", "HIATUS": "pausiert",
}
ATTRIBUTION = "Anime-Daten: AniList; Streaming-Angebote: JustWatch über TMDB"
