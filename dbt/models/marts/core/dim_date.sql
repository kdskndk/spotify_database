with spine as (

    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="to_date('2005-01-01', 'YYYY-MM-DD')",
        end_date="to_date('2031-01-01', 'YYYY-MM-DD')"
    ) }}

)

select
    to_char(date_day, 'YYYYMMDD')::int   as date_id,
    date_day::date                        as full_date,
    extract(year from date_day)::int      as year,
    extract(month from date_day)::int     as month,
    to_char(date_day, 'Month')            as month_name,
    extract(day from date_day)::int       as day,
    extract(isodow from date_day)::int    as day_of_week,
    to_char(date_day, 'Day')              as day_name,
    extract(week from date_day)::int      as week_of_year,
    extract(isodow from date_day) in (6, 7) as is_weekend
from spine
