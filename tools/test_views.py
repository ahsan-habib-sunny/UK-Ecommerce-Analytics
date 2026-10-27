"""Compose CREATE VIEW bodies into one WITH-chain and run a final query, read-only."""
import sys, re, pathlib, warnings
sys.path.insert(0, "loader"); warnings.filterwarnings("ignore")
from load_to_snowflake import connect, read_env, REPO_ROOT
text = "\n".join(pathlib.Path(f).read_text(encoding="utf-8") for f in sys.argv[1:-1])
text = re.sub(r"--[^\n]*", "", text).replace("UK_ECOM.STAGING.", "").replace("UK_ECOM.MARTS.", "")
views = re.findall(r"CREATE OR REPLACE VIEW (\w+)\s+AS\s+(.*?);", text, flags=re.S)
cte = ",\n".join(f"{name} AS (\n{body}\n)" for name, body in views)
final = sys.argv[-1]
conn = connect(read_env(REPO_ROOT / ".env")); cur = conn.cursor()
cur.execute(f"WITH {cte}\n{final}")
cols = [d[0] for d in cur.description]
print(" | ".join(cols))
for r in cur.fetchall(): print(" | ".join(str(x) for x in r))
