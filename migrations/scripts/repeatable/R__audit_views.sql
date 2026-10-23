-- Repeatable script: operational views over deployment and load metadata.
create or replace view `{{ project }}.{{ env }}_audit.deployment_history`
options (description = 'Migrations applied to this environment, newest first.')
as
select
    version,
    description,
    script,
    script_type,
    status,
    execution_time_ms,
    installed_by,
    installed_on
from `{{ project }}.{{ env }}_meta.change_history`
order by installed_on desc;

create or replace view `{{ project }}.{{ env }}_audit.load_summary`
options (description = 'Rows loaded per BRONZE table and day.')
as
select
    table_name,
    date(loaded_at) as load_date,
    count(*) as file_count,
    sum(row_count) as row_count,
    max(loaded_at) as last_loaded_at
from `{{ project }}.{{ env }}_audit.load_log`
group by table_name, load_date;
