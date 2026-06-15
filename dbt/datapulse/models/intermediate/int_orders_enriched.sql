with orders as (
    select * from {{ ref('stg_orders') }}
),
customers as (
    select * from {{ ref('stg_customers') }}
),
payments as (
    select * from {{ ref('stg_order_payments') }}
),
reviews_deduped as (
    -- Some orders have multiple reviews; keep the most recently answered one
    select *
    from {{ ref('stg_order_reviews') }}
    qualify row_number() over (
        partition by order_id
        order by review_answer_timestamp desc
    ) = 1
),
enriched as (
    select
        o.order_id,
        o.customer_id,
        c.customer_unique_id,
        c.customer_zip_code_prefix,
        c.customer_city,
        c.customer_state,
        o.order_status,
        o.order_purchase_timestamp,
        o.order_approved_at,
        o.order_delivered_carrier_date,
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date,
        o.days_to_deliver,
        o.seller_processing_days,
        o.delivered_on_time,
        o.is_delivery_date_missing,
        p.total_payment_value,
        p.max_installments,
        p.payment_method_count,
        p.used_credit_card,
        p.used_boleto,
        p.used_voucher,
        p.used_debit_card,
        r.review_id,
        r.review_score,
        r.review_comment_title,
        r.review_comment_message,
        case when r.review_id is not null then true else false end as has_review
    from orders o
    join customers c on o.customer_id = c.customer_id
    join payments p  on o.order_id = p.order_id
    left join reviews_deduped r on o.order_id = r.order_id
)
select * from enriched
