-- Spotify streaming history table
-- Source: full_output.csv (Spotify "extended streaming history" export)

CREATE SCHEMA IF NOT EXISTS source_data;

CREATE TABLE IF NOT EXISTS source_data.spotify_streaming_history (
    id                      SERIAL PRIMARY KEY,
    played_at               TIMESTAMPTZ NOT NULL,
    platform                TEXT,
    ms_played               INTEGER,
    track_name              TEXT,
    artist_name             TEXT,
    album_name              TEXT,
    track_uri               TEXT,
    reason_start            TEXT,
    reason_end              TEXT,
    shuffle                 BOOLEAN,
    skipped                 BOOLEAN,
    incognito_mode          BOOLEAN,
    source_file             TEXT
);

-- Genre/style lookups for albums, fetched from the Discogs API by
-- fetch_discogs_genres.py. One row per (album_name, artist_name) attempted --
-- match_status records whether a Discogs master release was found, so the
-- fetch script can skip already-processed albums on a rerun.
CREATE TABLE IF NOT EXISTS source_data.discogs_album_genres (
    id                      SERIAL PRIMARY KEY,
    artist_name             TEXT,
    album_name              TEXT NOT NULL,
    discogs_master_id       INTEGER,
    genres                  TEXT[],
    styles                  TEXT[],
    match_status            TEXT NOT NULL,
    fetched_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (artist_name, album_name)
);