{{ config(
    indexes=[
      {'columns': ['played_at']},
      {'columns': ['track_id']},
    ],
    post_hook="ANALYZE {{ this }}"
) }}

with streams as (

    select * from {{ ref('stg_spotify__streaming_history') }}

),

tracks as (

    select * from {{ ref('dim_tracks') }}

),

platforms as (

    select * from {{ ref('dim_platform') }}

),

reasons as (

    select * from {{ ref('dim_reason') }}

)

select
    streams.stream_source_id as stream_id,
    streams.played_at,
    to_char(streams.played_at, 'YYYYMMDD')::int as date_id,
    tracks.track_id,
    platforms.platform_id,
    reason_start.reason_id as reason_start_id,
    reason_end.reason_id   as reason_end_id,
    streams.ms_played,
    streams.shuffle,
    streams.skipped,
    streams.incognito_mode,
    streams.source_file
from streams
left join tracks
    on streams.track_uri = tracks.track_uri
left join platforms
    on streams.platform = platforms.platform_name
left join reasons as reason_start
    on streams.reason_start = reason_start.reason_value
left join reasons as reason_end
    on streams.reason_end = reason_end.reason_value
