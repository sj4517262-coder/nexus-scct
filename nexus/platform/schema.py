"""Namespaced source data with referential and uniqueness constraints."""
from sqlalchemy import MetaData, Table, Column, String, Integer, Float, Date, ForeignKey, ForeignKeyConstraint, Text
from threading import Lock

_schema_lock=Lock()

metadata = MetaData()
sources = Table("data_sources", metadata,
    Column("source_id",String,primary_key=True), Column("name",String,nullable=False),
    Column("url",Text,nullable=False), Column("license",String,nullable=False),
    Column("manifest",Text,nullable=False))
products = Table("m5_products", metadata,Column("product_id",String,primary_key=True),Column("source_id",String,ForeignKey("data_sources.source_id"),nullable=False),Column("native_id",String,unique=True,nullable=False),Column("department",String),Column("category",String))
stores = Table("m5_stores", metadata,Column("store_id",String,primary_key=True),Column("source_id",String,ForeignKey("data_sources.source_id"),nullable=False),Column("native_id",String,unique=True,nullable=False),Column("state",String))
series = Table("m5_series", metadata,Column("series_id",String,primary_key=True),Column("product_id",String,ForeignKey("m5_products.product_id"),nullable=False),Column("store_id",String,ForeignKey("m5_stores.store_id"),nullable=False))
calendar = Table("m5_calendar", metadata,Column("day",String,primary_key=True),Column("date",Date,unique=True,nullable=False),Column("week",Integer,nullable=False))
demand = Table("m5_demand", metadata,Column("series_id",String,ForeignKey("m5_series.series_id"),primary_key=True),Column("day",String,ForeignKey("m5_calendar.day"),primary_key=True),Column("units",Integer,nullable=False))
store_daily = Table("m5_store_daily",metadata,Column("store_id",String,ForeignKey("m5_stores.store_id"),primary_key=True),Column("date",Date,primary_key=True),Column("units",Integer,nullable=False))
prices = Table("m5_prices",metadata,Column("series_id",String,ForeignKey("m5_series.series_id"),primary_key=True),Column("week",Integer,primary_key=True),Column("price",Float,nullable=False))
logistics = Table("logistics_history", metadata,
    Column("id",String,primary_key=True),Column("source_id",String,ForeignKey("data_sources.source_id"),nullable=False),Column("order_id",String,nullable=False),Column("order_date",Date,nullable=False),
    Column("shipping_mode",String),Column("market",String),Column("region",String),Column("category",String),Column("scheduled_days",Integer),Column("actual_days",Integer),Column("quantity",Integer),Column("sales",Float),Column("late",Integer))
procurement = Table("procurement_history", metadata,
    Column("id",String,primary_key=True),Column("source_id",String,ForeignKey("data_sources.source_id"),nullable=False),Column("native_order_id",String),Column("vendor",String),Column("department",String),Column("fiscal_year",Integer),Column("paid_usd",Float),Column("pending_usd",Float))


def initialize(engine):
    with _schema_lock:
        with engine.begin() as connection:
            if connection.dialect.name=="postgresql":
                connection.exec_driver_sql("SELECT pg_advisory_xact_lock(72819403)")
            metadata.create_all(connection)


def upsert_frame(connection, table, frame):
    """Idempotent bulk upsert; PostgreSQL COPY staging for large historical files."""
    if frame.empty:
        return
    import io
    keys = [c.name for c in table.primary_key]
    if connection.dialect.name == "postgresql":
        name = table.name
        columns = list(frame.columns)
        cursor = connection.connection.cursor()
        cursor.execute(f'CREATE TEMP TABLE stage_{name} (LIKE {name} INCLUDING DEFAULTS) ON COMMIT DROP')
        buf = io.StringIO()
        frame.to_csv(buf,index=False,header=False,na_rep="\\N")
        buf.seek(0)
        cursor.copy_expert(f"COPY stage_{name} ({','.join(columns)}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')",buf)
        updates = [c for c in columns if c not in keys]
        clause = "DO UPDATE SET " + ",".join(f"{c}=EXCLUDED.{c}" for c in updates) if updates else "DO NOTHING"
        cursor.execute(f"INSERT INTO {name} ({','.join(columns)}) SELECT {','.join(columns)} FROM stage_{name} ON CONFLICT ({','.join(keys)}) {clause}")
        cursor.execute(f"DROP TABLE stage_{name}")
    else:
        from sqlalchemy.dialects.sqlite import insert
        records = frame.to_dict("records")
        for start in range(0,len(records),1000):
            statement = insert(table)
            update = {c.name:statement.excluded[c.name] for c in table.columns if c.name not in keys}
            statement = statement.on_conflict_do_update(index_elements=keys,set_=update) if update else statement.on_conflict_do_nothing(index_elements=keys)
            connection.execute(statement,records[start:start+1000])
