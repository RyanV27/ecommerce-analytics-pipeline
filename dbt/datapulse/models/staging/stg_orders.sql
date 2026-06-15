with source as (
    select * from {{ source('bronze', 'orders') }}
),
renamed as (
    select
        order_id,
        customer_id,
        order_status,
        timestamp(order_purchase_timestamp)       as order_purchase_timestamp,
        timestamp(order_approved_at)              as order_approved_at,
        timestamp(order_delivered_carrier_date)   as order_delivered_carrier_date,
        timestamp(order_delivered_customer_date)  as order_delivered_customer_date,
        timestamp(order_estimated_delivery_date)  as order_estimated_delivery_date,

        date_diff(
            date(timestamp(order_delivered_customer_date)),
            date(timestamp(order_purchase_timestamp)),
            day
        ) as days_to_deliver,

        date_diff(
            date(timestamp(order_delivered_carrier_date)),
            date(timestamp(order_approved_at)),
            day
        ) as seller_processing_days,

        case
            when timestamp(order_delivered_customer_date)
                 <= timestamp(order_estimated_delivery_date)
            then true
            else false
        end as delivered_on_time,

        case
            when order_status = 'delivered'
                 and order_delivered_customer_date is null
            then true
            else false
        end as is_delivery_date_missing

    from source
)
select * from renamed
