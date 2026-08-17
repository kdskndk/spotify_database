{{ config(
    indexes=[
      {'columns': ['album_id'], 'unique': True},
    ]
) }}

with albums as (

    select distinct
        album_name,
        artist_name
    from {{ ref('stg_spotify__streaming_history') }}
    where album_name is not null

),

artists as (

    select * from {{ ref('dim_artists') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['albums.album_name', 'albums.artist_name']) }} as album_id,
    albums.album_name,
    albums.artist_name,
    artists.artist_id
from albums
left join artists on albums.artist_name = artists.artist_name
