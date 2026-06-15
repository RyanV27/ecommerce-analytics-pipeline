with sellers as (
    select * from {{ ref('stg_sellers') }}
),
geo as (
    select * from {{ ref('stg_geolocation') }}
),
final as (
    select
        s.seller_id,
        s.seller_zip_code_prefix,
        s.seller_city,
        s.seller_state,
        g.lat as seller_lat,
        g.lng as seller_lng
    from sellers s
    left join geo g on s.seller_zip_code_prefix = g.zip_code_prefix
)
select * from final
