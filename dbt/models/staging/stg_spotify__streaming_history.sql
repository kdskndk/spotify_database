with source as (

    select * from {{ source('spotify', 'spotify_streaming_history') }}

),

renamed as (

    select
        id as stream_source_id,
        played_at,
        nullif(trim(platform), '')      as platform,
        ms_played,
        nullif(trim(track_name), '')    as track_name,
        nullif(trim(artist_name), '')   as artist_name,
        nullif(trim(album_name), '')    as album_name,
        nullif(trim(track_uri), '')     as track_uri,
        nullif(trim(reason_start), '')  as reason_start,
        nullif(trim(reason_end), '')    as reason_end,
        shuffle,
        skipped,
        incognito_mode,
        source_file

    from source

)

select * from renamed
