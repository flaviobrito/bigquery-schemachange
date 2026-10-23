-- Schema evolution example: the storefront started exporting marketing consent.
-- The matching column is declared in dbt/models/silver/ecommerce/_ecommerce__sources.yml;
-- removing it from either side is reported by the schema drift audit.
alter table `{{ project }}.{{ env }}_bronze.customers`
add column if not exists marketing_opt_in bool
options (description = 'Customer accepted marketing communication');
