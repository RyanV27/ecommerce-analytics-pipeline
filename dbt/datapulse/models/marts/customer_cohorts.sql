with cohort_base as (
    select
        c.customer_unique_id,
        date_trunc(min(date(o.order_purchase_timestamp)), month) as cohort_month
    from {{ ref('stg_orders') }} o
    join {{ ref('stg_customers') }} c on o.customer_id = c.customer_id
    group by c.customer_unique_id
),
customer_activity as (
    select
        c.customer_unique_id,
        date_trunc(date(o.order_purchase_timestamp), month) as activity_month
    from {{ ref('stg_orders') }} o
    join {{ ref('stg_customers') }} c on o.customer_id = c.customer_id
    where o.order_status = 'delivered'
    group by 1, 2
),
cohort_matrix as (
    select
        cb.cohort_month,
        date_diff(ca.activity_month, cb.cohort_month, month) as months_since_first,
        count(distinct ca.customer_unique_id)                 as active_customers
    from cohort_base cb
    join customer_activity ca on cb.customer_unique_id = ca.customer_unique_id
    group by 1, 2
)
select * from cohort_matrix
order by cohort_month, months_since_first
