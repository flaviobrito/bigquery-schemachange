-- Medallion layers. BRONZE is owned by migrations (raw landing tables);
-- SILVER, GOLD and AUDIT are populated by dbt.
{% for layer, description in [
    ('bronze', 'Raw landing layer: source-shaped data, loaded as-is with lineage metadata.'),
    ('silver', 'Cleaned, typed and deduplicated entities built by dbt.'),
    ('gold', 'Business-ready dimensional models and aggregates built by dbt.'),
    ('audit', 'Data quality results, schema drift monitoring and deployment logs.'),
] %}
create schema if not exists `{{ project }}.{{ env }}_{{ layer }}`
options (
    location = '{{ location }}',
    description = '{{ description }}',
    labels = [('layer', '{{ layer }}'), ('environment', '{{ env }}')]
);
{% endfor %}
