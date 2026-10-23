-- Always script: converges dataset labels on every deployment. Pull request
-- datasets also get a 7-day default table expiration as a cost safety net.
{% for layer in ['bronze', 'silver', 'gold', 'audit', 'meta'] %}
alter schema `{{ project }}.{{ env }}_{{ layer }}`
set options (
    labels = [('layer', '{{ layer }}'), ('environment', '{{ env }}'), ('managed_by', 'bqchange')],
    default_table_expiration_days = {{ 7 if env.startswith('pr_') else 'null' }}
);
{% endfor %}
