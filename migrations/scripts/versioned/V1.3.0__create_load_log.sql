-- Operational log written by ops/load_sample_data.py: one row per loaded file.
create table if not exists `{{ project }}.{{ env }}_audit.load_log` (
    table_name string not null,
    source_file string not null,
    row_count int64 not null,
    load_job_id string,
    loaded_at timestamp not null
)
partition by date(loaded_at)
options (description = 'Files loaded into BRONZE, one row per load job.');
