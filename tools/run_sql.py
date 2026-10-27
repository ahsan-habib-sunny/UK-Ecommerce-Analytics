"""Run a SQL file as ECOM_LOADER (read-only checks). Usage: run_sql.py file.sql [--show]"""
import sys, pathlib, warnings
sys.path.insert(0, "loader"); warnings.filterwarnings("ignore")
from load_to_snowflake import connect, read_env, REPO_ROOT
sql = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").replace("USE ROLE ECOM_DEVELOPER;", "")
conn = connect(read_env(REPO_ROOT / ".env"))
for i, cur in enumerate(conn.execute_string(sql, remove_comments=True), 1):
    rows = cur.fetchall() if cur.description else []
    print(f"stmt {i}: ok, {len(rows)} rows" + (f"  first: {rows[0]}" if rows and "--show" in sys.argv else ""))
