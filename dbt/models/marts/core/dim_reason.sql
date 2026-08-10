with reasons as (

    select distinct reason_start as reason_value
    from {{ ref('stg_spotify__streaming_history') }}
    where reason_start is not null

    union

    select distinct reason_end as reason_value
    from {{ ref('stg_spotify__streaming_history') }}
    where reason_end is not null

)

select
    {{ dbt_utils.generate_surrogate_key(['reason_value']) }} as reason_id,
    reason_value
from reasons
