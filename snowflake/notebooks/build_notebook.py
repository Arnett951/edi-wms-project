"""Builds wms_aging_snowpark.ipynb from the cells below (keeps the notebook diff-able).

    python snowflake/notebooks/build_notebook.py
"""
from pathlib import Path

import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("""# WMS inventory aging with Snowpark

The same inventory-aging logic as `WMSLAB.ANALYTICS.VW_INVENTORY_AGING`, the Power BI report and the
BI Publisher report, written in Python with the Snowpark DataFrame API.

Snowpark DataFrames are **lazy**. Each step below only builds a query plan. Snowflake turns the plan into SQL
and runs it on the warehouse when you call `.show()`, `.collect()`, `.to_pandas()` or `.save_as_table()`.
The data stays in Snowflake; only results come back.

Runs two ways:
- **In Snowsight** (Projects → Notebooks → Import .ipynb): picks up the notebook's own session.
- **Locally**: falls back to the lab's key-pair login (`~/.snowflake/wmslab_rsa_key.p8`)."""),

    code("""import os
from pathlib import Path

from snowflake.snowpark import Session, Window
from snowflake.snowpark import functions as F
from snowflake.snowpark.types import DateType, StringType

try:
    from snowflake.snowpark.context import get_active_session
    session = get_active_session()          # inside a Snowflake notebook
except Exception:
    from cryptography.hazmat.primitives import serialization
    key_path = Path(os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH", Path.home() / ".snowflake" / "wmslab_rsa_key.p8"))
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    session = Session.builder.configs({
        "account": os.environ.get("SNOWFLAKE_ACCOUNT", "rrtrzrl-tj58203"),
        "user": os.environ.get("SNOWFLAKE_USER", "CARNETT909"),
        "private_key": key.private_bytes(serialization.Encoding.DER,
                                         serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()),
    }).create()

session.use_role("WMSLAB_LOADER")
session.use_warehouse("WMSLAB_WH")
session.use_schema("WMSLAB.RAW")
session.query_tag = "wmslab-snowpark-notebook"
print(session.sql("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_SCHEMA()").collect()[0])"""),

    md("## 1. Tables as DataFrames\nNothing has run yet; these are just references."),
    code("""inv  = session.table("INVENTORY")
item = session.table("ITEM")
loc  = session.table("LOCATION")
wh   = session.table("WAREHOUSE")
lot  = session.table("LOT_ATTRIBUTE")

inv.show(5)"""),

    md("""## 2. The aging dataset in Python
A line-for-line translation of the SQL view: joins, a window function for the oldest receipt per
warehouse+SKU, ages computed against today, and the same 7-day minimum."""),
    code("""today = F.current_date()

aging = (
    inv.join(item, "ITEM_ID")
       .join(loc, "LOCATION_ID")
       .join(wh, "WAREHOUSE_ID")
       .join(lot, ["ITEM_ID", "LOT_NUMBER"], how="left")
       .with_column("OLDEST_RECEIVED_DATE",
                    F.min("RECEIVED_DATE").over(Window.partition_by("WAREHOUSE_CODE", "SKU")))
       .with_column("WAREHOUSE_AGE_DAYS", F.datediff("day", F.col("RECEIVED_DATE"), today))
       .with_column("TIRE_AGE_DAYS", F.datediff("day", F.col("MFG_DATE"), today))
       .with_column("AVAILABLE_QTY", F.iff(F.col("STOCK_STATUS") == "AVAILABLE",
                                           F.col("ON_HAND_QTY") - F.col("RESERVED_QTY"), F.lit(0)))
       .with_column("INVENTORY_VALUE", (F.col("ON_HAND_QTY") * F.col("UNIT_COST")).cast("NUMBER(14,2)"))
       .filter(F.col("WAREHOUSE_AGE_DAYS") >= 7)
       .select("WAREHOUSE_CODE", "WAREHOUSE_NAME", "SKU", "DESCRIPTION", "TIRE_SIZE",
               "LOCATION_CODE", "ZONE", "LOT_NUMBER", "DOT_CODE", "MFG_WEEK", "MFG_YEAR", "MFG_DATE",
               "RECEIVED_DATE", "OLDEST_RECEIVED_DATE", "WAREHOUSE_AGE_DAYS", "TIRE_AGE_DAYS",
               "STOCK_STATUS", "ON_HAND_QTY", "RESERVED_QTY", "AVAILABLE_QTY", "INVENTORY_VALUE")
)

# Still nothing has run. This is the SQL Snowpark will send:
print(aging.queries["queries"][-1][:1200], "...")"""),

    md("""## 3. Prove it matches the SQL view
`EXCEPT` in both directions. Zero rows each way means the Python and SQL versions return identical rows.
This is the same reconcile habit as the Azure SQL → Snowflake load, applied to logic instead of data."""),
    code("""view = session.table("WMSLAB.ANALYTICS.VW_INVENTORY_AGING").select(aging.columns)

only_python = aging.except_(view).count()
only_sql    = view.except_(aging).count()
print(f"rows: python={aging.count()}  view={view.count()}  only_in_python={only_python}  only_in_view={only_sql}")
assert only_python == 0 and only_sql == 0, "Snowpark and SQL view disagree"
"""),

    md("""## 4. Aging buckets by warehouse
The question an operations or finance user actually asks: how much money is sitting in each age band?"""),
    code("""age = F.col("WAREHOUSE_AGE_DAYS")
bucketed = aging.with_column(
    "AGE_BUCKET",
    F.when(age <= 30, F.lit("1: 7-30"))
     .when(age <= 60, F.lit("2: 31-60"))
     .when(age <= 90, F.lit("3: 61-90"))
     .when(age <= 180, F.lit("4: 91-180"))
     .otherwise(F.lit("5: 180+")),
)

buckets = (bucketed.group_by("WAREHOUSE_CODE", "AGE_BUCKET")
                   .agg(F.count("*").alias("LOTS"),
                        F.sum("ON_HAND_QTY").alias("UNITS"),
                        F.sum("INVENTORY_VALUE").alias("VALUE"))
                   .sort("WAREHOUSE_CODE", "AGE_BUCKET"))
buckets.show()"""),

    md("""## 5. Python running *inside* Snowflake: a UDF
Each DOT code ends in the manufacture week and year (`WWYY`, e.g. `DOT Y8X 1826` = week 18 of 2026).
This registers a Python function in Snowflake that decodes it, then uses it to check the stored `MFG_DATE`.
The function executes on the warehouse next to the data; the rows never come to this machine.
It's a data-quality check of the kind you'd run when a customer says "the ages look wrong.\""""),
    code("""from datetime import date

def dot_to_mfg_date(dot_code: str) -> date:
    \"\"\"Monday of the ISO week encoded in the last 4 digits of a DOT code (WWYY).\"\"\"
    if not dot_code:
        return None
    ww_yy = dot_code.strip()[-4:]
    if not ww_yy.isdigit():
        return None
    week, year = int(ww_yy[:2]), 2000 + int(ww_yy[2:])
    try:
        return date.fromisocalendar(year, week, 1)
    except ValueError:
        return None

dot_udf = session.udf.register(dot_to_mfg_date, return_type=DateType(), input_types=[StringType()],
                               name="DOT_TO_MFG_DATE", replace=True, is_permanent=False)

checked = lot.with_column("DECODED_MFG_DATE", dot_udf(F.col("DOT_CODE")))
mismatches = checked.filter(~F.equal_null(F.col("DECODED_MFG_DATE"), F.col("MFG_DATE")))
print(f"lots checked: {checked.count()}  DOT/MFG_DATE mismatches: {mismatches.count()}")
mismatches.show()"""),

    md("""## 6. Persist the result
`save_as_table` writes the bucket summary back to Snowflake, where any SQL user, BI tool or app
can query it. Snowpark generates a `CREATE TABLE AS SELECT` for this, so the data still never left."""),
    code("""buckets.write.save_as_table("WMSLAB.ANALYTICS.INVENTORY_AGING_BUCKETS", mode="overwrite")
session.table("WMSLAB.ANALYTICS.INVENTORY_AGING_BUCKETS").show()"""),

    md("""## 7. What it cost
Every statement above carries `QUERY_TAG = 'wmslab-snowpark-notebook'`, so query history shows exactly
what Snowpark sent and how long each statement took. This is the first place to look when a customer's
Python job is slow."""),
    code("""history = session.sql(\"\"\"
    SELECT query_type, COUNT(*) AS statements,
           ROUND(SUM(total_elapsed_time) / 1000, 2) AS elapsed_s,
           SUM(bytes_scanned) AS bytes_scanned
    FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION(RESULT_LIMIT => 1000))
    WHERE query_tag = 'wmslab-snowpark-notebook'
      AND execution_status = 'SUCCESS'   -- skip this query itself, still RUNNING
    GROUP BY query_type ORDER BY elapsed_s DESC
\"\"\")
history.show()"""),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
    "language_info": {"name": "python"},
})
out = Path(__file__).with_name("wms_aging_snowpark.ipynb")
nbf.write(nb, out)
print(f"wrote {out}")
