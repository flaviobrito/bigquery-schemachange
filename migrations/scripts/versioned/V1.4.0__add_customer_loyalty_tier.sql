-- The storefront launched a loyalty program and now exports the customer's tier.
alter table `{{ project }}.{{ env }}_bronze.customers`
add column if not exists loyalty_tier string
options (description = 'Loyalty program tier: bronze | silver | gold');
