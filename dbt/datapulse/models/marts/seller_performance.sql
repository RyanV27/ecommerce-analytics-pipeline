with order_items as (
    select * from {{ ref('stg_order_items') }}
),
orders as (
    select
        order_id,
        order_status,
        order_purchase_timestamp,
        days_to_deliver,
        seller_processing_days,
        delivered_on_time,
        review_score,
        has_review
    from {{ ref('fct_orders') }}
),
seller_metrics as (
    select
        oi.seller_id,
        count(distinct oi.order_id)                                        as total_orders,
        count(distinct oi.product_id)                                      as distinct_products,
        sum(oi.price)                                                      as total_revenue,
        avg(oi.price)                                                      as avg_item_price,
        sum(oi.freight_value)                                              as total_freight_collected,
        avg(o.days_to_deliver)                                             as avg_days_to_deliver,
        avg(o.seller_processing_days)                                      as avg_seller_processing_days,
        sum(case when o.delivered_on_time then 1 else 0 end)               as on_time_deliveries,
        count(case when o.order_status = 'delivered' then 1 end)           as delivered_orders,
        avg(o.review_score)                                                as avg_review_score,
        sum(case when o.has_review then 1 else 0 end)                      as reviewed_order_count,
        min(date(o.order_purchase_timestamp))                              as first_sale_date,
        max(date(o.order_purchase_timestamp))                              as last_sale_date
    from order_items oi
    left join orders o on oi.order_id = o.order_id
    group by oi.seller_id
),
final as (
    select
        sm.seller_id,
        sm.total_orders,
        sm.distinct_products,
        sm.total_revenue,
        sm.avg_item_price,
        sm.total_freight_collected,
        sm.avg_days_to_deliver,
        sm.avg_seller_processing_days,
        sm.on_time_deliveries,
        sm.delivered_orders,
        sm.avg_review_score,
        sm.reviewed_order_count,
        sm.first_sale_date,
        sm.last_sale_date,
        d.seller_city,
        d.seller_state,
        d.seller_lat,
        d.seller_lng,
        safe_divide(sm.on_time_deliveries, sm.delivered_orders) as on_time_rate
    from seller_metrics sm
    left join {{ ref('dim_sellers') }} d on sm.seller_id = d.seller_id
)
select * from final
