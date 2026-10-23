-- Blocks the build when a source layer (var('source_layers'), BRONZE here) and
-- the dbt sources disagree, e.g. a migration added a column that was not
-- declared in _ecommerce__sources.yml.
{{ config(tags=['schema_audit']) }}

select *
from {{ ref('audit_schema_drift') }}
where layer in ({{ "'" ~ var('source_layers') | join("', '") ~ "'" }})
    and drift_status != 'aligned'
