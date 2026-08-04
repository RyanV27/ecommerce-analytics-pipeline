## dbt conventions

- Staging models (`stg_*.sql`): one-to-one with source tables, do cleaning only — rename, cast, fix typos, add boolean flags
- Intermediate models (`int_*.sql`): complex joins; not exposed to BI tools
- Mart models: fact tables prefixed `fct_`, dimensions prefixed `dim_`
- Every primary key column must have `unique` + `not_null` dbt tests
- Every FK column must have a `relationships` test
- Target 90%+ column test coverage; run `dbt test` before committing model changes

## BigQuery SQL style

- Use `date_diff(current_date(), date_col, day)` for day differences (BigQuery syntax)
- Use `date_trunc(date_col, month)` for cohort bucketing
- Qualify all table references with dataset: `` `project.dataset.table` ``
- Replace `YOUR_PROJECT_ID` with the actual GCP project ID stored in `.env`
