-- ML training table for repeat-purchase propensity — leakage-safe forward-window design.
-- Features come from orders on/before snapshot T; label comes from the horizon window (T, T+horizon].
-- Do NOT use last_order_date or recency_days from dim_customers as model features against this label.
with date_bounds as (
    select max(date(order_purchase_timestamp)) as max_purchase_date
    from {{ ref('int_orders_enriched') }}
    where order_status = 'delivered'
),
snapshot_params as (
    select
        {% if var('repeat_snapshot_date') != '' %}
            date('{{ var("repeat_snapshot_date") }}')                                                         as T,
            date_add(date('{{ var("repeat_snapshot_date") }}'), interval {{ var('repeat_horizon_days') }} day) as T_plus_horizon
        {% else %}
            date_sub(max_purchase_date, interval {{ var('repeat_horizon_days') }} day)                        as T,
            max_purchase_date                                                                                  as T_plus_horizon
        {% endif %}
    from date_bounds
),
features as (
    select
        e.customer_unique_id,
        count(e.order_id)                                                          as frequency,
        sum(e.total_payment_value)                                                 as monetary,
        avg(e.total_payment_value)                                                 as avg_order_value,
        date_diff(p.T, min(date(e.order_purchase_timestamp)), day)                 as tenure_days,
        date_diff(p.T, max(date(e.order_purchase_timestamp)), day)                 as recency_at_T,
        avg(e.review_score)                                                        as avg_review_score,
        sum(case when e.has_review then 1 else 0 end)                              as reviewed_order_count,
        max(e.max_installments)                                                    as max_installments_used,
        max(e.used_credit_card)                                                    as used_credit_card,
        max(e.used_boleto)                                                         as used_boleto,
        max(e.used_voucher)                                                        as used_voucher
    from {{ ref('int_orders_enriched') }} e
    cross join snapshot_params p
    where e.order_status = 'delivered'
      and date(e.order_purchase_timestamp) <= p.T
    group by e.customer_unique_id, p.T
),
outcome as (
    -- Customers who made at least one purchase in the outcome window => WILL repeat
    select distinct e.customer_unique_id
    from {{ ref('int_orders_enriched') }} e
    cross join snapshot_params p
    where e.order_status = 'delivered'
      and date(e.order_purchase_timestamp) > p.T
      and date(e.order_purchase_timestamp) <= p.T_plus_horizon
),
final as (
    select
        f.customer_unique_id,
        f.frequency,
        f.monetary,
        f.avg_order_value,
        f.tenure_days,
        f.recency_at_T,
        f.avg_review_score,
        f.reviewed_order_count,
        f.max_installments_used,
        f.used_credit_card,
        f.used_boleto,
        f.used_voucher,
        p.T          as snapshot_date,
        p.T_plus_horizon as outcome_end_date,
        case when o.customer_unique_id is null then false else true end as will_repeat
    from features f
    cross join snapshot_params p
    left join outcome o on f.customer_unique_id = o.customer_unique_id
)
select * from final
