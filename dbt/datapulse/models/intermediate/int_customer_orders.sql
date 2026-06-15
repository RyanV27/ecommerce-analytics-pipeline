with enriched as (
    select * from {{ ref('int_orders_enriched') }}
    where order_status = 'delivered'
),
customer_agg as (
    select
        customer_unique_id,
        count(order_id)                                                       as order_count,
        sum(total_payment_value)                                              as total_spent,
        avg(total_payment_value)                                              as avg_order_value,
        min(date(order_purchase_timestamp))                                   as first_order_date,
        max(date(order_purchase_timestamp))                                   as last_order_date,
        date_diff(current_date(), max(date(order_purchase_timestamp)), day)   as recency_days,
        avg(review_score)                                                     as avg_review_score,
        sum(case when has_review then 1 else 0 end)                           as reviewed_order_count,
        count(order_id)                                                       as delivered_order_count,
        max(max_installments)                                                 as max_installments_used,
        max(used_credit_card)                                                 as used_credit_card,
        max(used_boleto)                                                      as used_boleto,
        max(used_voucher)                                                     as used_voucher
    from enriched
    group by customer_unique_id
)
select * from customer_agg
