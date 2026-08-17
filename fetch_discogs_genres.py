"""
Fetch genre/style metadata for every album in the analytics warehouse via the
Discogs API, and load the raw results into Postgres. Each album is matched to
a Discogs master release (the canonical work, not one specific pressing), and
its master-level genres/styles are stored.

Usage:
    python fetch_discogs_genres.py [--limit N] [--sleep SECONDS]

Requires: python3-discogs-client, psycopg2-binary  (pip install -r requirements.txt)

Auth (required):
    DISCOGS_TOKEN       Discogs personal access token.
                         Generate one at https://www.discogs.com/settings/developers
    DISCOGS_USER_AGENT  User-Agent string sent to the Discogs API
                         (default: spotify_analytics/1.0)

Connection settings are read from environment variables, with defaults
matching docker-compose.yml. Override them if your setup differs:
    PGHOST     (default: localhost)
    PGPORT     (default: 5432)
    PGDATABASE (default: spotify_history)
    PGUSER     (default: spotify)
    PGPASSWORD (default: spotify_pw)

This script reads its album list from analytics_marts.dim_albums, so run
`dbt run` at least once before using it.

It's resumable: it skips any (artist_name, album_name) pair already present
in source_data.discogs_album_genres, and commits after every album, so it
can be safely stopped (Ctrl+C) and restarted without losing progress or
re-spending API calls on albums already processed.

Discogs' authenticated rate limit is 60 requests/minute. Matching one album
costs two requests (search + master detail lookup -- genres/styles aren't
included in search results, so fetching them always triggers a follow-up
request), so a full run over thousands of albums will take hours. Test with
--limit first.
"""

import argparse
import os
import sys
import time

import discogs_client
import psycopg2
from discogs_client.exceptions import DiscogsAPIError


def get_pg_conn():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "spotify_history"),
        user=os.environ.get("PGUSER", "spotify"),
        password=os.environ.get("PGPASSWORD", "spotify_pw"),
    )


def get_discogs_client():
    token = os.environ.get("DISCOGS_TOKEN")
    if not token:
        sys.exit(
            "DISCOGS_TOKEN is not set. Generate a personal access token at "
            "https://www.discogs.com/settings/developers and set it as an "
            "environment variable before running this script."
        )
    user_agent = os.environ.get("DISCOGS_USER_AGENT", "spotify_analytics/1.0")
    return discogs_client.Client(user_agent, user_token=token)


def fetch_albums_to_process(conn, limit=None):
    with conn.cursor() as cur:
        cur.execute("""
            select distinct album_name, artist_name
            from analytics_marts.dim_albums
            where album_name is not null
            order by album_name, artist_name
        """)
        albums = cur.fetchall()

        cur.execute("select album_name, artist_name from source_data.discogs_album_genres")
        already_done = set(cur.fetchall())

    remaining = [a for a in albums if a not in already_done]
    if limit is not None:
        remaining = remaining[:limit]

    print(f"{len(albums)} albums total, {len(already_done)} already fetched, "
          f"{len(remaining)} to process this run.")
    return remaining


def lookup_album(client, album_name, artist_name):
    """Search Discogs for a master release matching this album. Returns
    (discogs_master_id, genres, styles); master_id is None on no match."""
    search_kwargs = {"release_title": album_name, "type": "master"}
    if artist_name:
        search_kwargs["artist"] = artist_name

    results = client.search(**search_kwargs)
    try:
        master = results[0]
    except IndexError:
        return None, [], []

    genres = master.genres or []
    styles = master.styles or []
    return master.id, genres, styles


def save_result(conn, album_name, artist_name, master_id, genres, styles, match_status):
    with conn.cursor() as cur:
        cur.execute("""
            insert into source_data.discogs_album_genres
                (album_name, artist_name, discogs_master_id, genres, styles, match_status)
            values (%s, %s, %s, %s, %s, %s)
            on conflict (album_name, artist_name) do nothing
        """, (album_name, artist_name, master_id, genres, styles, match_status))
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                         help="Only process this many albums (useful for a test run)")
    parser.add_argument("--sleep", type=float, default=1.0,
                         help="Seconds to sleep between albums (default: 1.0)")
    args = parser.parse_args()

    client = get_discogs_client()
    conn = get_pg_conn()

    albums = fetch_albums_to_process(conn, limit=args.limit)

    for i, (album_name, artist_name) in enumerate(albums, start=1):
        try:
            try:
                master_id, genres, styles = lookup_album(client, album_name, artist_name)
                match_status = "matched" if master_id else "no_match"
                save_result(conn, album_name, artist_name, master_id, genres, styles, match_status)

                if i % 25 == 0 or i == len(albums) or len(albums) <= 25:
                    print(f"  [{i}/{len(albums)}] {artist_name!r} - {album_name!r}: {match_status}")
            except DiscogsAPIError as e:
                print(f"  [{i}/{len(albums)}] ERROR on {artist_name!r} - {album_name!r}: {e}")

            time.sleep(args.sleep)
        except KeyboardInterrupt:
            print("\nStopped. Progress has been saved -- rerun the script to resume.")
            sys.exit(0)

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
