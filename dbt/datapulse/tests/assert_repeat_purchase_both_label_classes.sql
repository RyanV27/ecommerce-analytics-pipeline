-- Fail if the will_repeat label is not binary (both true and false must be present).
-- If the model only sees one class the XGBoost classifier cannot learn anything useful.
select 1
from (
    select count(distinct will_repeat) as c
    from {{ ref('repeat_purchase_training') }}
)
where c < 2
