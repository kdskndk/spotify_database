{{ config(
    indexes=[
      {'columns': ['album_id']},
    ]
) }}

with staging as (

    select * from {{ ref('stg_discogs__album_genres') }}
    where genre_type = 'style'

),

albums as (

    select * from {{ ref('dim_albums') }}

)

select
    albums.album_id,
    albums.album_name,
    albums.artist_id,
    albums.artist_name,
    staging.genre_value as style
from staging
inner join albums
    on staging.album_name = albums.album_name
    and staging.artist_name = albums.artist_name
