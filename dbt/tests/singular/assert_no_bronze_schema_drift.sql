-- Blocks the build when BRONZE and dbt sources disagree, e.g. a migration
-- added a column that was not declared in _ecommerce__sources.yml.
{{ config(tags=['schema_audit']) }}

select *
from {{ ref('audit_schema_drift') }}
where layer = 'bronze'
    and drift_status != 'aligned'
