with source as (

    select * from {{ source('discogs', 'album_genres') }}
    where match_status = 'matched'

),

genres as (

    select
        nullif(trim(album_name), '')  as album_name,
        nullif(trim(artist_name), '') as artist_name,
        'genre'                       as genre_type,
        unnest(genres)                as genre_value
    from source

),

styles as (

    select
        nullif(trim(album_name), '')  as album_name,
        nullif(trim(artist_name), '') as artist_name,
        'style'                       as genre_type,
        unnest(styles)                as genre_value
    from source

),

unioned as (

    select * from genres
    union all
    select * from styles

)

select
    album_name,
    artist_name,
    genre_type,
    nullif(trim(genre_value), '') as genre_value
from unioned
where genre_value is not null
