"""Upload the generated Parquet files to the Snowflake stage and COPY them into RAW.

    .venv/Scripts/python loader/load_to_snowflake.py            # load new files only
    .venv/Scripts/python loader/load_to_snowflake.py --reload   # empty RAW and load everything again

How it stays safe to re-run:
- PUT skips files that are already in the stage (same name).
- COPY INTO remembers which files it has loaded (for 64 days) and skips them.
So running it twice never duplicates rows, and a new month's file is the only thing loaded next time.

Connection settings come from .env in the repo root (see .env.example).
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pyarrow.parquet as pq
import snowflake.connector
from cryptography.hazmat.primitives import serialization

REPO_ROOT = Path(__file__).resolve().parents[1]
TABLES = ["postcode_areas", "products", "campaigns", "customers",
          "orders", "order_lines", "returns", "marketing_spend", "sessions"]
STAGE = "@UK_ECOM.RAW.STG_LANDING"


def read_env(path: Path) -> dict:
    """Minimal .env reader: KEY=VALUE lines, # comments."""
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return {**env, **{k: v for k, v in os.environ.items() if k.startswith("SNOWFLAKE_")}}


def connect(env: dict):
    key_path = Path(os.path.expanduser(env.get("SNOWFLAKE_PRIVATE_KEY_PATH", "~/.snowflake/ecom_loader_key.p8")))
    private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    return snowflake.connector.connect(
        account=env["SNOWFLAKE_ACCOUNT"],
        user=env.get("SNOWFLAKE_USER", "ECOM_LOADER"),
        private_key=private_key,
        role=env.get("SNOWFLAKE_ROLE", "ECOM_LOADER_ROLE"),
        warehouse=env.get("SNOWFLAKE_WAREHOUSE", "ECOM_TRANSFORM_WH"),
        database="UK_ECOM",
        schema="RAW",
        enable_server_session_keep_alive_auto_detection=False,   # no async queries: just log out on close
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=REPO_ROOT / "data" / "raw")
    ap.add_argument("--reload", action="store_true", help="truncate RAW tables and force-load every file")
    ap.add_argument("--tables", nargs="*", default=TABLES, help="subset of tables to load")
    args = ap.parse_args()

    conn = connect(read_env(REPO_ROOT / ".env"))
    cur = conn.cursor()
    print(f"Connected as {cur.execute('SELECT CURRENT_USER()').fetchone()[0]}\n")

    print(f"{'table':<16}{'files':>6}{'local rows':>13}{'loaded now':>13}{'rows in RAW':>13}{'secs':>7}")
    all_ok = True
    for table in args.tables:
        t0 = time.perf_counter()
        folder = args.data / table
        files = sorted(folder.glob("*.parquet"))
        local_rows = sum(pq.ParquetFile(f).metadata.num_rows for f in files)

        if args.reload:
            cur.execute(f"TRUNCATE TABLE {table}")
            cur.execute(f"REMOVE {STAGE}/{table}/")

        # 1. PUT: upload the local files to the internal stage (already Snappy-compressed)
        src = folder.as_posix() + "/*.parquet"
        cur.execute(f"PUT 'file://{src}' {STAGE}/{table}/ AUTO_COMPRESS = FALSE PARALLEL = 8")

        # 2. COPY INTO: load staged files into the RAW table, matching Parquet columns by name
        result = cur.execute(f"""
            COPY INTO {table}
            FROM {STAGE}/{table}/
            FILE_FORMAT = (FORMAT_NAME = 'UK_ECOM.RAW.FF_PARQUET')
            MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
            INCLUDE_METADATA = (_source_file = METADATA$FILENAME, _loaded_at = METADATA$START_SCAN_TIME)
            ON_ERROR = ABORT_STATEMENT
            {"FORCE = TRUE" if args.reload else ""}
        """).fetchall()
        loaded_now = sum(r[3] for r in result if len(r) > 3 and isinstance(r[3], int))

        in_raw = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        ok = in_raw == local_rows
        all_ok &= ok
        print(f"{table:<16}{len(files):>6}{local_rows:>13,}{loaded_now:>13,}{in_raw:>13,}{time.perf_counter() - t0:>7.1f}"
              f"  {'OK' if ok else 'MISMATCH'}")

    cur.close()
    conn.close()
    print("\nAll RAW tables match the local files." if all_ok else "\nSome tables don't match: see MISMATCH above.")


if __name__ == "__main__":
    main()
