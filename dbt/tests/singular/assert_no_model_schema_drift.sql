-- Fails when a SILVER or GOLD relation differs from its dbt contract, e.g.
-- someone ran ALTER TABLE directly in BigQuery. dbt would silently overwrite
-- the change on the next build; this test makes it visible first.
{{ config(tags=['schema_audit']) }}

select *
from {{ ref('audit_schema_drift') }}
where layer in ('silver', 'gold')
    and drift_status != 'aligned'
