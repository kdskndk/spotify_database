-- Many-to-many bridge: an album can have more than one genre/style, and a
-- genre/style applies to many albums, so this can't live as a column on
-- dim_albums or dim_genres directly.

{{ config(
    indexes=[
      {'columns': ['album_id']},
      {'columns': ['genre_id']},
    ]
) }}

with staging as (

    select * from {{ ref('stg_discogs__album_genres') }}

),

albums as (

    select * from {{ ref('dim_albums') }}

),

genres as (

    select * from {{ ref('dim_genres') }}

)

select distinct
    albums.album_id,
    genres.genre_id
from staging
inner join albums
    on staging.album_name = albums.album_name
    and staging.artist_name = albums.artist_name
inner join genres
    on staging.genre_type = genres.genre_type
    and staging.genre_value = genres.genre_value
