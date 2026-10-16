"""
Project 1 - Python ETL Tool (reference solution)
=================================================
Reads several related CSV files from a folder, cleans them, merges them into one
analysis-ready table, applies business logic, saves CSV + Excel + JSON, and logs
every step.

Data: the classic "Northwind" trading-company sample (real, public data) -
orders, order_details, customers, products and categories.

Run it from a terminal:
    python etl_tool.py
"""

import json
import logging
import re
import time
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

# ---- SECTION: config ----
CONFIG = {
    "base_dir": Path("etl_project"),          # everything lives under this folder
    "source_base_url": (
        "https://raw.githubusercontent.com/graphql-compose/graphql-compose-examples/"
        "master/examples/northwind/data/csv/"
    ),
    "source_files": ["orders", "order_details", "customers", "products", "categories"],
    # business rules - change them here, not deep inside the code
    "gold_threshold": 30000,
    "silver_threshold": 10000,
}


def get_paths(config):
    base = Path(config["base_dir"])
    return {
        "raw": base / "raw",
        "output": base / "output",
        "logs": base / "logs",
    }
# ---- END SECTION ----


# ---- SECTION: logging ----
def setup_logger(log_path, name="etl_tool"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()                      # avoid duplicate lines when re-run
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger


@contextmanager
def log_step(logger, step_name):
    # A custom context manager (Module 4): logs START / DONE / FAILED + duration.
    logger.info(f"START  {step_name}")
    started = time.time()
    try:
        yield
    except Exception:
        logger.error(f"FAILED {step_name}", exc_info=True)
        raise
    else:
        logger.info(f"DONE   {step_name} ({time.time() - started:.2f}s)")
# ---- END SECTION ----


# ---- SECTION: extract ----
def download_sample_data(raw_dir, config, logger):
    # Stand-in for "files arrive in a landing folder". Skips files already present.
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name in config["source_files"]:
        target = raw_dir / f"{name}.csv"
        if target.exists():
            logger.info(f"already downloaded: {target.name}")
            continue
        df = pd.read_csv(config["source_base_url"] + f"{name}.csv")
        df.to_csv(target, index=False)
        logger.info(f"downloaded {target.name}: {len(df)} rows")


def read_csv_folder(folder, logger):
    # Read EVERY csv in a folder -> dict {file_stem: DataFrame}
    folder = Path(folder)
    csv_files = sorted(folder.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {folder}")

    tables = {}
    for path in csv_files:
        df = pd.read_csv(path)
        tables[path.stem] = df
        logger.info(f"read {path.name}: {df.shape[0]} rows x {df.shape[1]} columns")
    return tables
# ---- END SECTION ----


# ---- SECTION: clean ----
def to_snake_case(name):
    # 'orderID' -> 'order_id', 'unitsInStock' -> 'units_in_stock'
    return re.sub(r"([a-z])([A-Z])", r"\1_\2", name).strip().lower()


def profile_table(df, name, logger):
    missing = df.isnull().sum()
    missing = missing[missing > 0].to_dict()
    logger.info(
        f"profile {name}: rows={len(df)}, duplicates={df.duplicated().sum()}, "
        f"columns_with_missing={missing if missing else 'none'}"
    )


def clean_table(df, name, logger, date_cols=(), numeric_cols=(), fill_values=None):
    rows_before = len(df)
    df = df.copy()

    # 1) consistent column names (so ALL column lists below use snake_case)
    df.columns = [to_snake_case(c) for c in df.columns]

    # 2) trim whitespace in text columns
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].str.strip()

    # 3) remove exact duplicate rows
    df = df.drop_duplicates()
    removed = rows_before - len(df)

    # 4) type casting
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 5) missing values - only where a sensible default exists
    if fill_values:
        df = df.fillna(fill_values)

    logger.info(f"clean {name}: {rows_before} -> {len(df)} rows ({removed} duplicates removed)")
    return df


def clean_all(tables, logger):
    for name, df in tables.items():
        profile_table(df, name, logger)

    cleaned = {
        "orders": clean_table(
            tables["orders"], "orders", logger,
            date_cols=["order_date", "required_date", "shipped_date"],
            numeric_cols=["freight"],
            fill_values={"ship_region": "N/A", "ship_postal_code": "N/A"},
            # NOTE: shipped_date is deliberately NOT filled - missing means "not shipped yet"
        ),
        "order_details": clean_table(
            tables["order_details"], "order_details", logger,
            numeric_cols=["unit_price", "quantity", "discount"],
        ),
        "customers": clean_table(
            tables["customers"], "customers", logger,
            fill_values={"region": "N/A", "postal_code": "N/A", "fax": "N/A"},
        ),
        "products": clean_table(
            tables["products"], "products", logger,
            numeric_cols=["unit_price", "units_in_stock", "reorder_level"],
        ),
        "categories": clean_table(tables["categories"], "categories", logger),
    }
    return cleaned
# ---- END SECTION ----


# ---- SECTION: merge ----
def build_order_lines(tables, logger):
    # One row per order line, enriched with order, customer, product and category info.
    lines = tables["order_details"].rename(columns={"unit_price": "sale_unit_price"})
    expected_rows = len(lines)

    orders = tables["orders"][
        ["order_id", "customer_id", "order_date", "required_date", "shipped_date",
         "freight", "ship_country"]
    ]
    customers = tables["customers"][
        ["customer_id", "company_name", "city", "country"]
    ].rename(columns={"city": "customer_city", "country": "customer_country"})
    products = tables["products"][
        ["product_id", "product_name", "category_id", "units_in_stock",
         "reorder_level", "discontinued"]
    ]
    categories = tables["categories"][["category_id", "category_name"]]

    merged = (
        lines
        .merge(orders, on="order_id", how="left", validate="many_to_one")
        .merge(customers, on="customer_id", how="left", validate="many_to_one")
        .merge(products, on="product_id", how="left", validate="many_to_one")
        .merge(categories, on="category_id", how="left", validate="many_to_one")
    )

    # Data-quality guard: left joins on many-to-one keys must NOT change the row count
    if len(merged) != expected_rows:
        raise ValueError(f"Merge changed row count: {expected_rows} -> {len(merged)}")

    unmatched = merged["company_name"].isnull().sum() + merged["product_name"].isnull().sum()
    logger.info(f"merge: {len(merged)} order lines x {merged.shape[1]} columns, unmatched keys={unmatched}")
    return merged
# ---- END SECTION ----


# ---- SECTION: business ----
def classify_delivery(row):
    if pd.isnull(row["shipped_date"]):
        return "Not Shipped"
    if row["shipped_date"] > row["required_date"]:
        return "Late"
    return "On Time"


def classify_stock(row):
    if row["discontinued"] == 1:
        return "Discontinued"
    if row["units_in_stock"] <= row["reorder_level"]:
        return "Reorder"
    return "OK"


def classify_customer(total_revenue, config):
    if total_revenue >= config["gold_threshold"]:
        return "Gold"
    if total_revenue >= config["silver_threshold"]:
        return "Silver"
    return "Bronze"


def apply_business_logic(df, config, logger):
    df = df.copy()

    # --- calculations ---
    df["line_total"] = (df["sale_unit_price"] * df["quantity"] * (1 - df["discount"])).round(2)
    df["discount_amount"] = (df["sale_unit_price"] * df["quantity"] * df["discount"]).round(2)
    df["order_month"] = df["order_date"].dt.to_period("M").astype(str)
    df["days_to_ship"] = (df["shipped_date"] - df["order_date"]).dt.days

    # --- classifications ---
    df["delivery_status"] = df.apply(classify_delivery, axis=1)
    df["stock_status"] = df.apply(classify_stock, axis=1)

    customer_revenue = df.groupby("customer_id")["line_total"].sum()
    tier_by_customer = customer_revenue.map(lambda value: classify_customer(value, config))
    df["customer_tier"] = df["customer_id"].map(tier_by_customer)

    logger.info(
        "business logic: total revenue={:,.2f}; delivery={}; tiers={}".format(
            df["line_total"].sum(),
            df["delivery_status"].value_counts().to_dict(),
            tier_by_customer.value_counts().to_dict(),
        )
    )
    return df


def build_summaries(df, logger):
    summaries = {
        "revenue_by_category": (
            df.groupby("category_name")
              .agg(revenue=("line_total", "sum"), units=("quantity", "sum"),
                   orders=("order_id", "nunique"))
              .round(2).sort_values("revenue", ascending=False).reset_index()
        ),
        "revenue_by_country": (
            df.groupby("customer_country")
              .agg(revenue=("line_total", "sum"), customers=("customer_id", "nunique"))
              .round(2).sort_values("revenue", ascending=False).reset_index()
        ),
        "revenue_by_month": (
            df.groupby("order_month").agg(revenue=("line_total", "sum"))
              .round(2).reset_index()
        ),
        "delivery_performance": (
            df.drop_duplicates("order_id")["delivery_status"]
              .value_counts().rename_axis("delivery_status").reset_index(name="orders")
        ),
        "customer_tiers": (
            df.groupby(["customer_tier", "customer_id", "company_name"])
              .agg(revenue=("line_total", "sum")).round(2)
              .sort_values("revenue", ascending=False).reset_index()
        ),
    }
    logger.info(f"summaries built: {list(summaries)}")
    return summaries
# ---- END SECTION ----


# ---- SECTION: load ----
def save_outputs(df, summaries, out_dir, logger):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "order_lines_clean.csv"
    df.to_csv(csv_path, index=False)
    logger.info(f"saved CSV   -> {csv_path} ({csv_path.stat().st_size:,} bytes)")

    excel_path = out_dir / "etl_report.xlsx"
    with pd.ExcelWriter(excel_path) as writer:           # context manager again
        df.to_excel(writer, sheet_name="order_lines", index=False)
        for sheet_name, summary_df in summaries.items():
            summary_df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    logger.info(f"saved Excel -> {excel_path} ({excel_path.stat().st_size:,} bytes)")

    json_path = out_dir / "etl_summary.json"
    payload = {
        "total_revenue": round(float(df["line_total"].sum()), 2),
        "order_lines": int(len(df)),
        "orders": int(df["order_id"].nunique()),
        "customers": int(df["customer_id"].nunique()),
        "summaries": {
            name: json.loads(s.to_json(orient="records")) for name, s in summaries.items()
        },
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"saved JSON  -> {json_path} ({json_path.stat().st_size:,} bytes)")
    return {"csv": csv_path, "excel": excel_path, "json": json_path}
# ---- END SECTION ----


# ---- SECTION: pipeline ----
def run_pipeline(config=CONFIG, download=True):
    paths = get_paths(config)
    for folder in paths.values():
        folder.mkdir(parents=True, exist_ok=True)

    logger = setup_logger(paths["logs"] / "etl_run.log")
    logger.info("=== ETL run started ===")
    started = time.time()

    try:
        if download:
            with log_step(logger, "0. download sample data"):
                download_sample_data(paths["raw"], config, logger)

        with log_step(logger, "1. extract (read all CSVs)"):
            raw_tables = read_csv_folder(paths["raw"], logger)

        with log_step(logger, "2. clean"):
            clean_tables = clean_all(raw_tables, logger)

        with log_step(logger, "3. merge"):
            order_lines = build_order_lines(clean_tables, logger)

        with log_step(logger, "4. business logic"):
            enriched = apply_business_logic(order_lines, config, logger)
            summaries = build_summaries(enriched, logger)

        with log_step(logger, "5. save outputs"):
            outputs = save_outputs(enriched, summaries, paths["output"], logger)

        logger.info(f"=== ETL run finished OK in {time.time() - started:.2f}s ===")
        return enriched, summaries, outputs

    except Exception:
        logger.critical("=== ETL run FAILED ===")
        raise
    finally:
        for handler in logger.handlers:
            handler.flush()


if __name__ == "__main__":
    run_pipeline()
# ---- END SECTION ----
