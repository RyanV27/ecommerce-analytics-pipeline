with source as (
    select * from {{ source('bronze', 'order_payments') }}
),
aggregated as (
    select
        order_id,
        sum(payment_value)                                                as total_payment_value,
        max(payment_installments)                                         as max_installments,
        count(distinct payment_type)                                      as payment_method_count,
        max(case when payment_type = 'credit_card' then 1 else 0 end)    as used_credit_card,
        max(case when payment_type = 'boleto'      then 1 else 0 end)    as used_boleto,
        max(case when payment_type = 'voucher'     then 1 else 0 end)    as used_voucher,
        max(case when payment_type = 'debit_card'  then 1 else 0 end)    as used_debit_card
    from source
    group by order_id
)
select * from aggregated
