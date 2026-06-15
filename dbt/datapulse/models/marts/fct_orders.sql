with enriched as (
    select * from {{ ref('int_orders_enriched') }}
),
items_agg as (
    select
        order_id,
        count(*)                    as item_count,
        sum(price)                  as items_revenue,
        sum(freight_value)          as total_freight,
        count(distinct product_id)  as distinct_products,
        count(distinct seller_id)   as distinct_sellers
    from {{ ref('stg_order_items') }}
    group by order_id
),
final as (
    select
        e.order_id,
        e.customer_unique_id,
        e.customer_city,
        e.customer_state,
        e.order_status,
        e.order_purchase_timestamp,
        e.order_approved_at,
        e.order_delivered_carrier_date,
        e.order_delivered_customer_date,
        e.order_estimated_delivery_date,
        e.days_to_deliver,
        e.seller_processing_days,
        e.delivered_on_time,
        e.is_delivery_date_missing,
        e.total_payment_value,
        e.max_installments,
        e.payment_method_count,
        e.used_credit_card,
        e.used_boleto,
        e.used_voucher,
        e.used_debit_card,
        e.review_score,
        e.has_review,
        ia.item_count,
        ia.items_revenue,
        ia.total_freight,
        ia.distinct_products,
        ia.distinct_sellers,
        date_trunc(date(e.order_purchase_timestamp), month) as order_month
    from enriched e
    left join items_agg ia on e.order_id = ia.order_id
)
select * from final
