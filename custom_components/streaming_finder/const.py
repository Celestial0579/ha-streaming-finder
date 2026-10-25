"""Konstanten für den Streaming-Finder."""

DOMAIN = "streaming_finder"

CONF_TMDB_TOKEN = "tmdb_token"
CONF_LAND = "land"
CONF_SPRACHE = "sprache"

DEFAULT_LAND = "DE"
DEFAULT_SPRACHE = "de-DE"

DIENST_WO_LAEUFT = "wo_laeuft"
DIENST_ANIME_SAISON = "anime_saison"

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
