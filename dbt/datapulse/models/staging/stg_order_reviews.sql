with source as (
    select * from {{ source('bronze', 'order_reviews') }}
),
renamed as (
    select
        review_id,
        order_id,
        review_score,
        review_comment_title,
        review_comment_message,
        timestamp(review_creation_date)    as review_creation_date,
        timestamp(review_answer_timestamp) as review_answer_timestamp
    from source
)
select * from renamed
