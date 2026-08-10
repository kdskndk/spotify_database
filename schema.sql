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