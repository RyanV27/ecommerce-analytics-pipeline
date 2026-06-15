with items as (
    select * from {{ ref('stg_order_items') }}
),
orders as (
    select
        order_id,
        customer_unique_id,
        order_status,
        order_purchase_timestamp,
        order_month
    from {{ ref('fct_orders') }}
),
products as (
    select
        product_id,
        product_category_name,
        product_category_name_english
    from {{ ref('dim_products') }}
),
final as (
    select
        i.order_id,
        i.order_item_id,
        i.product_id,
        i.seller_id,
        o.customer_unique_id,
        o.order_status,
        o.order_purchase_timestamp,
        o.order_month,
        p.product_category_name,
        p.product_category_name_english,
        i.shipping_limit_date,
        i.price,
        i.freight_value,
        i.total_item_value
    from items i
    left join orders o   on i.order_id = o.order_id
    left join products p on i.product_id = p.product_id
)
select * from final
