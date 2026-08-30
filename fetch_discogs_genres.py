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

Matching tries four strategies in order, keeping the first that finds
something (see lookup_album() for details): a master-release search, then a
release-level search scored by genre/style tag count, the same release
search again with punctuation stripped from the artist/album name (Discogs'
search can fail to match names like "Tyler, The Creator" on the comma even
though the release exists under that name), and finally -- if the artist is
found on Discogs at all -- a full crawl of that artist's discography for an
exact title match, bypassing Discogs' text search entirely (which can fail
to index titles that are purely punctuation/symbols, e.g. "+/-").

Discogs' authenticated rate limit is 60 requests/minute. The master search
costs two requests (search + detail lookup, since genres/styles aren't
included in search results). Falling back to a release search costs one
request per page of results plus one per candidate release scored. The
discography-crawl fallback costs one request per page of the artist's
release list (prolific artists can run to dozens of pages) -- so an album
that fails all the way through can be considerably more expensive than one
that matches early. A full run over thousands of albums will take hours.
Test with --limit first.
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata

import discogs_client
import psycopg2
from discogs_client.exceptions import DiscogsAPIError, HTTPError
from requests.exceptions import RequestException


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


def normalize_title(s):
    """Lowercase, punctuation-free form of a title, used to compare a
    release's title against the album name we're looking for."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip().lower()


def strip_punctuation(s):
    """Remove punctuation/special characters from a search query, keeping
    words space-separated. Discogs' search sometimes fails to match names
    that include punctuation it doesn't index on (e.g. the comma in
    "Tyler, The Creator") even though the release exists under that name."""
    if not s:
        return s
    cleaned = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


def titles_match(a, b):
    """Compare two titles for an exact match. Falls back to a raw,
    case-insensitive comparison when normalization strips both down to
    nothing (titles that are purely punctuation/symbols, e.g. "+/-") --
    otherwise every such title would spuriously match every other one."""
    norm_a, norm_b = normalize_title(a), normalize_title(b)
    if norm_a or norm_b:
        return norm_a == norm_b
    return (a or "").strip().lower() == (b or "").strip().lower()


MAX_RELEASE_CANDIDATES_SCORED = 10


def best_release_match(client, album_name, artist_name):
    """Search Discogs releases (not masters) for album_name/artist_name,
    filter to releases that plausibly match, and return the one with the
    most combined genre + style tags -- different pressings of the same
    album can be tagged with differing completeness on Discogs.

    Uses a free-text query (rather than the field-scoped release_title/
    artist search params) because the field-scoped artist search can fail
    to match artist names containing certain special characters (e.g. the
    "$$" in "Joey Bada$$") even though the release exists under that name.
    /database/search always returns release titles as "Artist - Title", so
    matching checks that the normalized title ends with the album name and
    (if given) contains the artist name, rather than an exact-equality
    check against the bare album name.

    Returns (discogs_id, genres, styles); discogs_id is None on no match."""
    query = " ".join(p for p in (artist_name, album_name) if p)
    if not query:
        return None, [], []

    candidates = client.search(q=query, type="release").page(1)

    target = normalize_title(album_name)
    artist_norm = normalize_title(artist_name)

    def is_match(candidate):
        title = normalize_title(candidate.title)
        if not target or not title.endswith(target):
            return False
        return not artist_norm or artist_norm in title

    matches = [c for c in candidates if is_match(c)]

    best_id, best_genres, best_styles, best_score = None, [], [], -1
    for release in matches[:MAX_RELEASE_CANDIDATES_SCORED]:
        genres = release.genres or []
        styles = release.styles or []
        score = len(genres) + len(styles)
        if score > best_score:
            master = release.master
            best_id = master.id if master else release.id
            best_genres, best_styles, best_score = genres, styles, score

    return best_id, best_genres, best_styles


MAX_ARTIST_SEARCH_PAGES = 3
MAX_ARTIST_RELEASE_PAGES = 50


def resolve_artist(client, artist_name):
    """Find the Discogs artist whose name exactly matches artist_name
    (case-insensitively, among the first few pages of an artist search).
    Returns an Artist object, or None if no exact-name match is found."""
    if not artist_name:
        return None

    target = artist_name.strip().lower()
    results = client.search(q=artist_name, type="artist")
    for page_index in range(1, min(results.pages, MAX_ARTIST_SEARCH_PAGES) + 1):
        for candidate in results.page(page_index):
            name = candidate.data.get("title") or candidate.data.get("name") or ""
            if name.strip().lower() == target:
                return client.artist(candidate.id)

    return None


def discography_match(client, album_name, artist_name):
    """Last-resort fallback: resolve the artist directly and page through
    their full Discogs discography (releases and masters both), matching by
    exact title. This guarantees that if the artist is found on Discogs but
    nothing here matches, it's a genuine gap in Discogs' own search index
    rather than a limitation of the query-based tiers above -- Discogs' text
    search can fail to surface a release even though it's listed on the
    artist's own page (e.g. it doesn't seem to index titles that are purely
    punctuation/symbols, like "+/-").

    This is expensive: one request to resolve the artist, plus one request
    per page of their release list (capped at MAX_ARTIST_RELEASE_PAGES) --
    prolific artists can run to dozens of pages. Only worth trying after the
    cheaper search-based tiers have failed.
    Returns (discogs_id, genres, styles); discogs_id is None on no match."""
    artist = resolve_artist(client, artist_name)
    if artist is None:
        return None, [], []

    releases = artist.releases
    for page_index in range(1, min(releases.pages, MAX_ARTIST_RELEASE_PAGES) + 1):
        for item in releases.page(page_index):
            if not titles_match(item.data.get("title"), album_name):
                continue

            genres = item.genres or []
            styles = item.styles or []
            if item.data.get("type") == "master":
                discogs_id = item.id
            else:
                master = item.master
                discogs_id = master.id if master else item.id
            return discogs_id, genres, styles

    return None, [], []


def lookup_album(client, album_name, artist_name):
    """Match this album to a Discogs release, trying four strategies in
    order and stopping at the first that finds something:
      1. Master search (the original method): search Discogs masters by
         artist + release title, taking the first candidate that resolves --
         Discogs' search index can point to a master that's since been
         merged into another one and no longer exists, so a 404 on one
         candidate falls through to the next rather than aborting.
      2. Release search: list Discogs releases (not masters) for the artist,
         filter to ones whose title matches the album, and take the one with
         the most genre/style tags.
      3. Same as (2), but with punctuation stripped from the artist/album
         name first.
      4. Discography crawl: resolve the artist directly and scan their full
         release list for an exact title match, bypassing Discogs' text
         search entirely. Expensive, so tried only if 1-3 all fail.
    Returns (discogs_id, genres, styles, match_method); discogs_id is None
    and match_method is "no_match" if nothing was found."""
    search_kwargs = {"release_title": album_name, "type": "master"}
    if artist_name:
        search_kwargs["artist"] = artist_name

    for master in client.search(**search_kwargs).page(1):
        try:
            return master.id, master.genres or [], master.styles or [], "master"
        except HTTPError as e:
            if e.status_code != 404:
                raise
            continue

    release_id, genres, styles = best_release_match(client, album_name, artist_name)
    if release_id:
        return release_id, genres, styles, "release"

    stripped_album = strip_punctuation(album_name)
    stripped_artist = strip_punctuation(artist_name)
    release_id, genres, styles = best_release_match(client, stripped_album, stripped_artist)
    if release_id:
        return release_id, genres, styles, "release_stripped"

    discogs_id, genres, styles = discography_match(client, album_name, artist_name)
    if discogs_id:
        return discogs_id, genres, styles, "discography"

    return None, [], [], "no_match"


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
                master_id, genres, styles, match_status = lookup_album(client, album_name, artist_name)
                save_result(conn, album_name, artist_name, master_id, genres, styles, match_status)

                if i % 25 == 0 or i == len(albums) or len(albums) <= 25:
                    print(f"  [{i}/{len(albums)}] {artist_name!r} - {album_name!r}: {match_status}")
            except (DiscogsAPIError, json.JSONDecodeError, RequestException) as e:
                # Covers Discogs API errors plus transient failures (a 5xx/empty
                # response, or a dropped connection) that the discogs_client
                # library doesn't retry on its own -- such an album is left
                # unsaved and will simply be retried on the next run.
                print(f"  [{i}/{len(albums)}] ERROR on {artist_name!r} - {album_name!r}: "
                      f"{type(e).__name__}: {e}")

            time.sleep(args.sleep)
        except KeyboardInterrupt:
            print("\nStopped. Progress has been saved -- rerun the script to resume.")
            sys.exit(0)

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
