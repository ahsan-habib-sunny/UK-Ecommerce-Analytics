# UK E-commerce Analytics

End-to-end analytics build: synthetic UK e-commerce data (~8M rows) → Snowflake → Microsoft Fabric → Power BI.

```
Python generator (seeded) → Parquet
  → Snowflake internal stage → COPY INTO RAW
  → STAGING views (typing, dedupe, data-quality fixes)
  → MARTS views (star schema)
  → Dataflow Gen2 (incremental) → Lakehouse
  → Semantic model (incremental refresh, calc groups, field parameters, dynamic RLS)
  → Report → App
```

## Repo layout

| Folder       | Contents                                                  |
|--------------|-----------------------------------------------------------|
| `snowflake/` | SQL scripts, numbered in run order                        |
| `generator/` | Python data generator (data output is git-ignored)        |
| `dataflows/` | Dataflow Gen2 definitions / Power Query M                 |
| `pbip/`      | Power BI Project (PBIP) files: the report and model as text |
| `docs/`      | Data dictionary, design notes, screenshots                |

## Generating the data

The data is synthetic and reproducible: the same seed always gives the same rows. Nothing generated is committed to Git.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r generator/requirements.txt     # Windows (Git Bash)
.venv/Scripts/python generator/generate.py --scale 0.0125             # ~100k rows, a few seconds
.venv/Scripts/python generator/validate.py                            # row counts and integrity checks
.venv/Scripts/python generator/generate.py                            # full ~8.1M rows, ~30 seconds
```

Output: Parquet files in `data/raw/<table>/`, one file per month for the large tables.

_Work in progress. A full write-up comes at the end of the project._
