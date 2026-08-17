{{ config(
    indexes=[
      {'columns': ['genre_id'], 'unique': True},
    ]
) }}

with genres as (

    select distinct
        genre_type,
        genre_value
    from {{ ref('stg_discogs__album_genres') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['genre_type', 'genre_value']) }} as genre_id,
    genre_type,
    genre_value
from genres
