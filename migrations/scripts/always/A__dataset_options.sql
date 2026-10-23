-- Always script: converges dataset labels on every deployment, for every layer
-- declared in `layers` (migrations/bqchange.yml) plus bqchange's meta dataset.
-- Pull request datasets also get a 7-day default table expiration as a cost safety net.
{% for layer, dataset in (layers | dictsort) + [('meta', env ~ '_meta')] %}
alter schema `{{ project }}.{{ dataset }}`
set options (
    labels = [('layer', '{{ layer }}'), ('environment', '{{ env }}'), ('managed_by', 'bqchange')],
    default_table_expiration_days = {{ 7 if env.startswith('pr_') else 'null' }}
);
{% endfor %}
