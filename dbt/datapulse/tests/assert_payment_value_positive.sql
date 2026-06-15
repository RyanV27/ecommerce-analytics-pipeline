{{ config(severity='warn') }}
-- 3 orders in the Olist dataset have $0 total payment (cancelled/free orders). Warn rather than fail.
select
    order_id,
    total_payment_value
from {{ ref('stg_order_payments') }}
where total_payment_value <= 0
