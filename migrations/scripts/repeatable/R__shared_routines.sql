-- Repeatable script: re-applied whenever its rendered content changes.
-- Persistent UDF shared by dbt models and data quality tests.
create or replace function `{{ project }}.{{ env }}_audit.is_valid_email`(email string)
returns bool
options (description = 'True when the value looks like an email address.')
as (
    regexp_contains(lower(trim(email)), r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$')
);
