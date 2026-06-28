-- Fail if tenure_days < recency_at_T for any customer.
-- tenure_days = days since first order; recency_at_T = days since last order.
-- First order cannot be more recent than last order, so tenure >= recency always.
select customer_unique_id
from {{ ref('repeat_purchase_training') }}
where tenure_days < recency_at_T
