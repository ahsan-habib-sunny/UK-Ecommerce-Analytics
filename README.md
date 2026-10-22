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

_Work in progress. A full write-up comes at the end of the project._
