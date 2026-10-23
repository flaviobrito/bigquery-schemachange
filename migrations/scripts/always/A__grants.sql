-- Always script: read access to GOLD for the configured principal, re-applied
-- on every deployment so privileges converge to this definition.
{% if reader_principal %}
grant `roles/bigquery.dataViewer`
on schema `{{ project }}.{{ env }}_gold`
to "{{ reader_principal }}";
{% else %}
select 'BQ_READER_PRINCIPAL not set: no GOLD grants applied' as status;
{% endif %}
