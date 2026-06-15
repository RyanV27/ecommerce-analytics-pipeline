with source as (
    select * from {{ source('bronze', 'sellers') }}
),
renamed as (
    select
        seller_id,
        seller_zip_code_prefix,
        lower(trim(seller_city)) as seller_city,
        upper(seller_state)      as seller_state
    from source
)
select * from renamed
