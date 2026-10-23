{% import "modules/bronze.sql" as bronze %}
-- Raw landing tables mirroring the e-commerce operational system exports.
-- Columns stay close to the source contract; typing and cleaning happen in SILVER.
create table if not exists `{{ project }}.{{ env }}_bronze.customers` (
    customer_id string not null options (description = 'Natural key from the storefront'),
    first_name string,
    last_name string,
    email string,
    phone string,
    country_code string options (description = 'ISO 3166-1 alpha-2'),
    state string,
    city string,
    created_at timestamp,
    updated_at timestamp,
    {{ bronze.metadata_columns() }}
)
{{ bronze.landing_options('customer_id', 'Storefront customer accounts.') }};

create table if not exists `{{ project }}.{{ env }}_bronze.products` (
    product_id string not null,
    sku string,
    product_name string,
    category string,
    brand string,
    unit_price numeric,
    unit_cost numeric,
    is_active bool,
    created_at timestamp,
    updated_at timestamp,
    {{ bronze.metadata_columns() }}
)
{{ bronze.landing_options('product_id', 'Product catalog.') }};

create table if not exists `{{ project }}.{{ env }}_bronze.orders` (
    order_id string not null,
    customer_id string,
    order_status string
        options (description = 'placed | paid | shipped | delivered | cancelled | returned'),
    order_channel string options (description = 'web | mobile_app | marketplace'),
    currency_code string,
    shipping_amount numeric,
    discount_amount numeric,
    ordered_at timestamp,
    updated_at timestamp,
    {{ bronze.metadata_columns() }}
)
{{ bronze.landing_options('order_id', 'Order headers.') }};

create table if not exists `{{ project }}.{{ env }}_bronze.order_items` (
    order_item_id string not null,
    order_id string,
    product_id string,
    quantity int64,
    unit_price numeric options (description = 'Price charged at order time'),
    {{ bronze.metadata_columns() }}
)
{{ bronze.landing_options('order_id', 'Order line items.') }};

create table if not exists `{{ project }}.{{ env }}_bronze.payments` (
    payment_id string not null,
    order_id string,
    payment_method string
        options (description = 'credit_card | debit_card | pix | boleto | paypal'),
    payment_status string options (description = 'approved | declined | refunded'),
    amount numeric,
    paid_at timestamp,
    {{ bronze.metadata_columns() }}
)
{{ bronze.landing_options('order_id', 'Payment transactions.') }};
