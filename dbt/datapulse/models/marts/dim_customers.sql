with customer_orders as (
    select * from {{ ref('int_customer_orders') }}
),
customers_deduped as (
    -- One address row per unique customer — pick the most recent customer_id
    select
        customer_unique_id,
        customer_zip_code_prefix,
        customer_city,
        customer_state
    from {{ ref('stg_customers') }}
    qualify row_number() over (
        partition by customer_unique_id
        order by customer_id desc
    ) = 1
),
geo as (
    select * from {{ ref('stg_geolocation') }}
),
final as (
    select
        co.customer_unique_id,
        c.customer_zip_code_prefix,
        c.customer_city,
        c.customer_state,
        g.lat                                                           as customer_lat,
        g.lng                                                           as customer_lng,
        co.order_count                                                  as frequency,
        co.total_spent                                                  as monetary,
        co.avg_order_value,
        co.recency_days,
        co.first_order_date,
        co.last_order_date,
        co.avg_review_score,
        co.reviewed_order_count,
        co.delivered_order_count,
        co.max_installments_used,
        co.used_credit_card,
        co.used_boleto,
        co.used_voucher,
        case when co.order_count > 1 then true else false end           as is_repeat_customer,
        case when co.recency_days > 90 then true else false end         as is_churned
    from customer_orders co
    left join customers_deduped c on co.customer_unique_id = c.customer_unique_id
    left join geo g on c.customer_zip_code_prefix = g.zip_code_prefix
)
select * from final
