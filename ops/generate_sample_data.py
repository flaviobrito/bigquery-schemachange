"""Deterministic synthetic e-commerce data matching the BRONZE table columns.

Example:
    python -m ops.generate_sample_data --output-dir data/sample --customers 500 --orders 3000
    python -m ops.generate_sample_data --inject-anomalies   # exercise data quality tests
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from faker import Faker

logger = logging.getLogger(__name__)

# Data columns of each BRONZE table (lineage columns are added by the loader).
COLUMNS: dict[str, list[str]] = {
    "customers": [
        "customer_id", "first_name", "last_name", "email", "phone", "country_code",
        "state", "city", "created_at", "updated_at", "marketing_opt_in",
    ],
    "products": [
        "product_id", "sku", "product_name", "category", "brand", "unit_price",
        "unit_cost", "is_active", "created_at", "updated_at",
    ],
    "orders": [
        "order_id", "customer_id", "order_status", "order_channel", "currency_code",
        "shipping_amount", "discount_amount", "ordered_at", "updated_at",
    ],
    "order_items": ["order_item_id", "order_id", "product_id", "quantity", "unit_price"],
    "payments": ["payment_id", "order_id", "payment_method", "payment_status", "amount", "paid_at"],
}  # fmt: skip

CATEGORIES = ["electronics", "home", "fashion", "beauty", "sports", "books", "toys"]
CHANNELS = {"web": 0.5, "mobile_app": 0.35, "marketplace": 0.15}
STATUSES = {
    "delivered": 0.55, "shipped": 0.15, "paid": 0.1, "placed": 0.07,
    "cancelled": 0.08, "returned": 0.05,
}  # fmt: skip
PAYMENT_METHODS = {
    "credit_card": 0.45, "pix": 0.3, "debit_card": 0.1, "boleto": 0.1, "paypal": 0.05,
}  # fmt: skip
PAID_STATUSES = {"paid", "shipped", "delivered", "returned"}

Row = dict[str, object]


@dataclass
class Dataset:
    tables: dict[str, list[Row]] = field(default_factory=lambda: {name: [] for name in COLUMNS})


def money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def weighted(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def generate(
    customers: int = 500,
    products: int = 60,
    orders: int = 3000,
    days: int = 120,
    seed: int = 42,
    inject_anomalies: bool = False,
    now: datetime | None = None,
) -> Dataset:
    rng = random.Random(seed)
    fake = Faker("en_US")
    fake.seed_instance(seed)
    now = (now or datetime.now(UTC)).replace(tzinfo=None, microsecond=0)
    start = now - timedelta(days=days)
    data = Dataset()

    for index in range(1, customers + 1):
        created_at = fake.date_time_between(start_date=start - timedelta(days=365), end_date=start)
        data.tables["customers"].append(
            {
                "customer_id": f"C{index:06d}",
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "email": fake.unique.email(),
                "phone": fake.phone_number(),
                "country_code": "US",
                "state": fake.state_abbr(),
                "city": fake.city(),
                "created_at": timestamp(created_at),
                "updated_at": timestamp(created_at),
                "marketing_opt_in": rng.random() < 0.4,
            }
        )

    for index in range(1, products + 1):
        price = money(rng.uniform(9.9, 899.0))
        data.tables["products"].append(
            {
                "product_id": f"P{index:05d}",
                "sku": f"SKU-{index:05d}",
                "product_name": fake.catch_phrase(),
                "category": rng.choice(CATEGORIES),
                "brand": fake.company(),
                "unit_price": price,
                "unit_cost": money(price * Decimal(str(rng.uniform(0.35, 0.75)))),
                "is_active": rng.random() < 0.92,
                "created_at": timestamp(start - timedelta(days=400)),
                "updated_at": timestamp(start - timedelta(days=rng.randint(0, 30))),
            }
        )

    item_sequence = 0
    payment_sequence = 0
    product_rows = data.tables["products"]
    for index in range(1, orders + 1):
        order_id = f"O{index:07d}"
        ordered_at = fake.date_time_between(start_date=start, end_date=now)
        status = weighted(rng, STATUSES)

        items_amount = Decimal("0")
        for product in rng.sample(product_rows, k=min(rng.randint(1, 4), len(product_rows))):
            item_sequence += 1
            quantity = rng.randint(1, 3)
            unit_price = product["unit_price"]
            items_amount += unit_price * quantity
            data.tables["order_items"].append(
                {
                    "order_item_id": f"OI{item_sequence:08d}",
                    "order_id": order_id,
                    "product_id": product["product_id"],
                    "quantity": quantity,
                    "unit_price": unit_price,
                }
            )

        discount = money(items_amount * Decimal("0.1")) if rng.random() < 0.2 else money(0)
        shipping = money(0) if items_amount >= 200 else money(rng.choice([9.9, 14.9, 19.9]))
        order_total = items_amount - discount + shipping
        data.tables["orders"].append(
            {
                "order_id": order_id,
                "customer_id": f"C{rng.randint(1, customers):06d}",
                "order_status": status,
                "order_channel": weighted(rng, CHANNELS),
                "currency_code": "USD",
                "shipping_amount": shipping,
                "discount_amount": discount,
                "ordered_at": timestamp(ordered_at),
                "updated_at": timestamp(ordered_at + timedelta(hours=rng.randint(1, 72))),
            }
        )

        method = weighted(rng, PAYMENT_METHODS)
        paid_at = ordered_at + timedelta(minutes=rng.randint(1, 90))
        attempts: list[tuple[str, Decimal]] = []
        if status in PAID_STATUSES:
            if rng.random() < 0.08:
                attempts.append(("declined", order_total))
            attempts.append(("approved", order_total))
            if status == "returned":
                attempts.append(("refunded", order_total))
        elif status == "cancelled" and rng.random() < 0.5:
            attempts.append(("declined", order_total))

        for offset, (payment_status, amount) in enumerate(attempts):
            payment_sequence += 1
            data.tables["payments"].append(
                {
                    "payment_id": f"PAY{payment_sequence:08d}",
                    "order_id": order_id,
                    "payment_method": method,
                    "payment_status": payment_status,
                    "amount": money(amount),
                    "paid_at": timestamp(paid_at + timedelta(minutes=offset * 5)),
                }
            )

    # Realistic noise that SILVER is expected to absorb (deduplication, cleanup).
    for customer in rng.sample(data.tables["customers"], k=max(1, customers // 50)):
        stale = dict(customer, city=fake.city(), updated_at=customer["created_at"])
        data.tables["customers"].append(stale)
        customer["updated_at"] = timestamp(now - timedelta(days=rng.randint(1, 30)))

    if inject_anomalies:
        _inject_anomalies(data, rng)

    return data


def _inject_anomalies(data: Dataset, rng: random.Random) -> None:
    """Break data on purpose so warn/error data quality tests have something to catch."""
    for customer in rng.sample(data.tables["customers"], k=5):
        customer["email"] = str(customer["email"]).replace("@", " at ")
    orphan = dict(rng.choice(data.tables["orders"]), order_id="O9999999", customer_id="C999999")
    data.tables["orders"].append(orphan)
    rng.choice(data.tables["order_items"])["unit_price"] = money(-10)
    rng.choice(data.tables["orders"])["order_status"] = "lost_in_transit"


def write_csv(data: Dataset, output_dir: Path, batch_id: str) -> list[Path]:
    paths = []
    for table, columns in COLUMNS.items():
        table_dir = output_dir / table
        table_dir.mkdir(parents=True, exist_ok=True)
        path = table_dir / f"{table}_{batch_id}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data.tables[table])
        paths.append(path)
        logger.info("Wrote %s rows to %s", len(data.tables[table]), path)
    return paths


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/sample"))
    parser.add_argument("--customers", type=int, default=500)
    parser.add_argument("--products", type=int, default=60)
    parser.add_argument("--orders", type=int, default=3000)
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--inject-anomalies", action="store_true")
    args = parser.parse_args()

    data = generate(
        customers=args.customers,
        products=args.products,
        orders=args.orders,
        days=args.days,
        seed=args.seed,
        inject_anomalies=args.inject_anomalies,
    )
    write_csv(data, args.output_dir, datetime.now(UTC).strftime("%Y%m%dT%H%M%S"))


if __name__ == "__main__":
    main()
