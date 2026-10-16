import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text

# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[1]
M5_DIR = BASE_DIR / "data" / "raw" / "m5"

SALES_FILE = M5_DIR / "sales_train_validation.csv"
CALENDAR_FILE = M5_DIR / "calendar.csv"

# ---------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------
DATABASE_URL = (
    "postgresql+psycopg2://"
    "nexus:change-this-password@localhost:5432/nexus_db"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# ---------------------------------------------------------
# Load calendar
# ---------------------------------------------------------
print("Loading calendar...")

calendar = pd.read_csv(
    CALENDAR_FILE,
    usecols=["date", "d"]
)

calendar["date"] = pd.to_datetime(calendar["date"])

date_map = dict(
    zip(calendar["d"], calendar["date"])
)

print(f"Calendar rows: {len(calendar):,}")

# ---------------------------------------------------------
# Determine latest 365 days available in validation sales
# ---------------------------------------------------------
# sales_train_validation.csv ends at d_1913.
# Therefore, select the latest 365 days from d_1 ... d_1913.

sales_day_columns = [
    column
    for column in pd.read_csv(
        SALES_FILE,
        nrows=0
    ).columns
    if column.startswith("d_")
]

sales_day_columns = sorted(
    sales_day_columns,
    key=lambda x: int(x.split("_")[1])
)

day_columns = sales_day_columns[-365:]

selected_days = calendar[
    calendar["d"].isin(day_columns)
]

print(
    f"Loading {len(day_columns)} days "
    f"from {selected_days['date'].min().date()} "
    f"to {selected_days['date'].max().date()}"
)
# ---------------------------------------------------------
# Load sales
# ---------------------------------------------------------
print("Loading sales file...")

sales = pd.read_csv(
    SALES_FILE,
    usecols=[
        "item_id",
        "dept_id",
        "cat_id",
        "store_id",
        "state_id",
        *day_columns,
    ],
)

print(f"Sales rows: {len(sales):,}")

# ---------------------------------------------------------
# Convert wide → long
# ---------------------------------------------------------
print("Converting sales to long format...")

id_columns = [
    "item_id",
    "dept_id",
    "cat_id",
    "store_id",
    "state_id",
]

demand = sales.melt(
    id_vars=id_columns,
    value_vars=day_columns,
    var_name="d",
    value_name="units_sold",
)

# ---------------------------------------------------------
# Map M5 day → actual date
# ---------------------------------------------------------
demand["demand_date"] = demand["d"].map(date_map)

# ---------------------------------------------------------
# Rename to project terminology
# ---------------------------------------------------------
demand = demand.rename(
    columns={
        "item_id": "product_id",
        "store_id": "store_id",
        "dept_id": "department_id",
        "cat_id": "category_id",
        "state_id": "state_id",
    }
)

# ---------------------------------------------------------
# Keep only required columns
# ---------------------------------------------------------
demand = demand[
    [
        "demand_date",
        "product_id",
        "store_id",
        "department_id",
        "category_id",
        "state_id",
        "units_sold",
    ]
]

# ---------------------------------------------------------
# Data types
# ---------------------------------------------------------
demand["demand_date"] = pd.to_datetime(demand["demand_date"])
demand["units_sold"] = demand["units_sold"].astype("int32")

# ---------------------------------------------------------
# Remove duplicate rows
# ---------------------------------------------------------
demand = demand.drop_duplicates(
    subset=[
        "demand_date",
        "product_id",
        "store_id",
    ]
)

print(f"Prepared rows: {len(demand):,}")

# ---------------------------------------------------------
# Insert into PostgreSQL
# ---------------------------------------------------------
print("Loading into PostgreSQL...")

demand.to_sql(
    "m5_demand_history",
    engine,
    if_exists="append",
    index=False,
    chunksize=50_000,
    method="multi",
)

print("M5 ingestion completed successfully.")

# ---------------------------------------------------------
# Verification
# ---------------------------------------------------------
with engine.connect() as connection:

    result = connection.execute(
        text(
            """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT product_id) AS products,
                COUNT(DISTINCT store_id) AS stores,
                MIN(demand_date) AS first_date,
                MAX(demand_date) AS last_date,
                SUM(units_sold) AS total_units
            FROM m5_demand_history
            """
        )
    )

    row = result.fetchone()

    print("\n========== M5 DATABASE SUMMARY ==========")
    print(f"Rows       : {row.total_rows:,}")
    print(f"Products   : {row.products:,}")
    print(f"Stores     : {row.stores:,}")
    print(f"First date : {row.first_date}")
    print(f"Last date  : {row.last_date}")
    print(f"Total units: {row.total_units:,}")
    print("=========================================")