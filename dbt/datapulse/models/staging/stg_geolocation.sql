with source as (
    select * from {{ source('bronze', 'geolocation') }}
),
deduplicated as (
    select
        geolocation_zip_code_prefix as zip_code_prefix,
        avg(geolocation_lat)        as lat,
        avg(geolocation_lng)        as lng,
        max(geolocation_state)      as state,
        max(geolocation_city)       as city
    from source
    group by geolocation_zip_code_prefix
)
select * from deduplicated
