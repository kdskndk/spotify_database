"""
Load full_output.csv (Spotify streaming history) into PostgreSQL.

Usage:
    python load_csv.py /path/to/full_output.csv

Requires: pandas, psycopg2-binary  (pip install -r requirements.txt)

Connection settings are read from environment variables, with defaults
matching docker-compose.yml. Override them if your setup differs:
    PGHOST     (default: localhost)
    PGPORT     (default: 5432)
    PGDATABASE (default: spotify_history)
    PGUSER     (default: spotify)
    PGPASSWORD (default: spotify_pw)
"""

import io
import os
import sys

import pandas as pd
import psycopg2

csv_path = "/app/full_output.csv"

# Columns in the final table, in the exact order the CSV maps to.
# (Unnamed: 0 from the CSV is dropped -- Postgres generates its own id.)
TABLE_COLUMNS = [
    "played_at", "platform", "ms_played",
    "track_name", "artist_name", "album_name", "track_uri",
    "reason_start", "reason_end", "shuffle", "skipped",
    "incognito_mode", "source_file",
]

CSV_TO_TABLE_RENAME = {
    "ts": "played_at",
    "master_metadata_track_name": "track_name",
    "master_metadata_album_artist_name": "artist_name",
    "master_metadata_album_album_name": "album_name",
    "spotify_track_uri": "track_uri"
}


def load_and_clean(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, low_memory=False)

    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])

    df = df.rename(columns=CSV_TO_TABLE_RENAME)

    # ts -> proper timestamp
    df["played_at"] = pd.to_datetime(df["played_at"], utc=True, errors="coerce")

    # ms_played -> integer
    df["ms_played"] = pd.to_numeric(df["ms_played"], errors="coerce").astype("Int64")

    # bool columns that should already be clean booleans
    for col in ("shuffle", "skipped", "incognito_mode"):
        df[col] = df[col].astype("boolean")

    # keep only the columns we're loading, in table order
    df = df[TABLE_COLUMNS]

    return df


def load_to_postgres(df: pd.DataFrame):
    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "spotify_history"),
        user=os.environ.get("PGUSER", "spotify"),
        password=os.environ.get("PGPASSWORD", "spotify_pw"),
    )
    try:
        with conn.cursor() as cur:
            # Fast bulk load via COPY, using an in-memory CSV buffer
            buffer = io.StringIO()
            df.to_csv(buffer, index=False, header=False, na_rep="\\N")
            buffer.seek(0)

            cur.copy_expert(
                f"COPY source_data.spotify_streaming_history ({', '.join(TABLE_COLUMNS)}) "
                f"FROM STDIN WITH (FORMAT csv, NULL '\\N')",
                buffer,
            )
        conn.commit()
        print(f"Loaded {len(df)} rows into spotify_streaming_history.")
    finally:
        conn.close()

print(f"Reading and cleaning {csv_path} ...")
cleaned_df = load_and_clean(csv_path)
print(f"Cleaned {len(cleaned_df)} rows. Loading into Postgres ...")
load_to_postgres(cleaned_df)
