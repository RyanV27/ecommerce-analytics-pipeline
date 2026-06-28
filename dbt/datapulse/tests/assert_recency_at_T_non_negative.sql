-- Fail if any row has recency_at_T < 0 (customer's last order is after snapshot date T).
-- This would indicate a data leakage bug in the snapshot_params CTE.
select customer_unique_id
from {{ ref('repeat_purchase_training') }}
where recency_at_T < 0
