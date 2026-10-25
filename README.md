# Streaming-Finder für Home Assistant

Beantwortet zwei Fragen – für Automationen und den Sprachassistenten:

- **„Wo läuft …?“** – bei welchen Streamingdiensten eine Serie oder ein Film in deinem Land verfügbar ist
  (Abo, kostenlos, mit Werbung, leihen, kaufen).
- **„Welche Animes laufen diese Season?“** – die beliebtesten Titel einer Season mit Status, nächster Folge und
  Plattformen.

*English summary below.*

## Aktionen

| Aktion | Felder | Antwort |
|---|---|---|
| `streaming_finder.wo_laeuft` | `titel`, `art` (serie/film/egal), `jahr` | bis zu drei Treffer mit Titel, Jahr und `angebote` (abo, kostenlos, mit_werbung, leihen, kaufen) |
| `streaming_finder.anime_saison` | `saison` (Winter/Frühling/Sommer/Herbst, leer = aktuelle), `jahr`, `anzahl` | Titel, Format, Folgen, Status, nächste Folge, Genres, Bewertung, Plattformen weltweit und – mit TMDB – im Land |

## Datenquellen

- **[AniList](https://anilist.co)** (GraphQL, ohne Konto) für die Anime-Seasons
- **[TMDB](https://www.themoviedb.org)** für Titel und Streaming-Angebote je Land; die Angebote stammen von
  **JustWatch**. Dafür ist ein kostenloser TMDB-Schlüssel nötig (API Read Access Token).

Ergebnisse werden zwischengespeichert (Season 6 h, Angebote 12 h), damit die Dienste geschont werden.

This product uses the TMDB API but is not endorsed or certified by TMDB. Streaming-Angebote: JustWatch.

## Einrichtung

1. HACS › **Benutzerdefinierte Repositories** › diese Repository-URL, Typ **Integration**; installieren, neu starten.
2. **Einstellungen › Geräte & Dienste › Integration hinzufügen › Streaming-Finder**: Land (z. B. `DE`), Sprache
   (z. B. `de-DE`), optional den TMDB-Schlüssel. Er lässt sich später unter **Konfigurieren** nachtragen.

---

## English summary

Two response actions: `streaming_finder.wo_laeuft` (which streaming services offer a series or film in your country,
via TMDB/JustWatch – needs a free TMDB API read access token) and `streaming_finder.anime_saison` (most popular anime
of a season from AniList, with country availability when a TMDB key is set). Set up from the UI after installing via
HACS as a custom repository (type *Integration*).

Lizenz / License: MIT
