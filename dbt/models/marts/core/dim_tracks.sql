-- The same track_uri can appear with more than one track_name/album_name/artist_name
-- combination over time (label re-releases, metadata corrections upstream in Spotify's
-- data). track_id is derived from track_uri alone, so we pick a single canonical name
-- variant per track_uri here -- the most frequently logged one, tie-broken by most
-- recently played -- to keep track_uri unique in this table and avoid fan-out when
-- fact_streams joins back on it.

{{ config(
    indexes=[
      {'columns': ['track_id'], 'unique': True},
    ]
) }}

with tracks as (

    select
        track_uri,
        track_name,
        album_name,
        artist_name,
        played_at
    from {{ ref('stg_spotify__streaming_history') }}
    where track_uri is not null

),

variants as (

    select
        track_uri,
        track_name,
        album_name,
        artist_name,
        count(*) as variant_count,
        max(played_at) as last_played_at
    from tracks
    group by track_uri, track_name, album_name, artist_name

),

ranked as (

    select
        *,
        row_number() over (
            partition by track_uri
            order by variant_count desc, last_played_at desc
        ) as rn
    from variants

),

albums as (

    select * from {{ ref('dim_albums') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['ranked.track_uri']) }} as track_id,
    ranked.track_name,
    ranked.track_uri,
    albums.album_id
from ranked
left join albums
    on ranked.album_name = albums.album_name
    and ranked.artist_name = albums.artist_name
where ranked.rn = 1
