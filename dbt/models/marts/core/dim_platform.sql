with platforms as (

    select distinct
        platform
    from {{ ref('stg_spotify__streaming_history') }}
    where platform is not null

)

select
    {{ dbt_utils.generate_surrogate_key(['platform']) }} as platform_id,
    platform as platform_name
from platforms
