with source as (
    select * from {{ source('bronze', 'order_items') }}
),
renamed as (
    select
        order_id,
        order_item_id,
        product_id,
        seller_id,
        timestamp(shipping_limit_date) as shipping_limit_date,
        price,
        freight_value,
        price + freight_value          as total_item_value
    from source
)
select * from renamed
