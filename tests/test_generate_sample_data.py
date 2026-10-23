from datetime import datetime
from decimal import Decimal

from ops.generate_sample_data import COLUMNS, PAID_STATUSES, generate, write_csv

NOW = datetime(2026, 1, 31, 12, 0, 0)


def small_dataset(**kwargs):
    return generate(customers=40, products=15, orders=200, seed=7, now=NOW, **kwargs)


def test_generation_is_deterministic():
    assert small_dataset().tables == small_dataset().tables


def test_rows_follow_bronze_column_order():
    data = small_dataset()
    for table, columns in COLUMNS.items():
        assert all(list(row) == columns for row in data.tables[table]), table


def test_referential_integrity():
    data = small_dataset()
    customer_ids = {row["customer_id"] for row in data.tables["customers"]}
    product_ids = {row["product_id"] for row in data.tables["products"]}
    order_ids = {row["order_id"] for row in data.tables["orders"]}

    assert {row["customer_id"] for row in data.tables["orders"]} <= customer_ids
    assert {row["product_id"] for row in data.tables["order_items"]} <= product_ids
    assert {row["order_id"] for row in data.tables["order_items"]} <= order_ids
    assert {row["order_id"] for row in data.tables["payments"]} <= order_ids


def test_paid_orders_have_payment_matching_total():
    data = small_dataset()
    items_by_order: dict[str, Decimal] = {}
    for item in data.tables["order_items"]:
        amount = item["unit_price"] * item["quantity"]
        items_by_order[item["order_id"]] = items_by_order.get(item["order_id"], 0) + amount
    approved = {
        row["order_id"]: row["amount"]
        for row in data.tables["payments"]
        if row["payment_status"] == "approved"
    }

    for order in data.tables["orders"]:
        if order["order_status"] in PAID_STATUSES:
            total = items_by_order[order["order_id"]] - order["discount_amount"]
            assert approved[order["order_id"]] == total + order["shipping_amount"]


def test_customer_duplicates_are_older_versions():
    data = small_dataset()
    latest: dict[str, str] = {}
    for row in data.tables["customers"]:
        latest[row["customer_id"]] = max(latest.get(row["customer_id"], ""), row["updated_at"])
    assert len(data.tables["customers"]) > len(latest)


def test_anomalies_are_injected_only_on_request():
    clean = small_dataset()
    broken = small_dataset(inject_anomalies=True)
    assert all(row["unit_price"] >= 0 for row in clean.tables["order_items"])
    assert any(row["unit_price"] < 0 for row in broken.tables["order_items"])
    assert any(row["customer_id"] == "C999999" for row in broken.tables["orders"])


def test_write_csv_creates_one_file_per_table(tmp_path):
    paths = write_csv(small_dataset(), tmp_path, "test")
    assert {path.parent.name for path in paths} == set(COLUMNS)
    header = (tmp_path / "orders" / "orders_test.csv").read_text().splitlines()[0]
    assert header == ",".join(COLUMNS["orders"])
