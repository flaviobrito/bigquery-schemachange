-- Fails when a dbt-built layer (SILVER, GOLD here) differs from its contract, e.g.
-- someone ran ALTER TABLE directly in BigQuery. dbt would silently overwrite
-- the change on the next build; this test makes it visible first.
{{ config(tags=['schema_audit']) }}

select *
from {{ ref('audit_schema_drift') }}
where layer not in ({{ "'" ~ var('source_layers') | join("', '") ~ "'" }})
    and drift_status != 'aligned'
