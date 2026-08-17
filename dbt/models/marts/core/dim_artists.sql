{{ config(
    indexes=[
      {'columns': ['artist_id'], 'unique': True},
    ]
) }}

with artists as (

    select distinct
        artist_name
    from {{ ref('stg_spotify__streaming_history') }}
    where artist_name is not null

)

select
    {{ dbt_utils.generate_surrogate_key(['artist_name']) }} as artist_id,
    artist_name
from artists
