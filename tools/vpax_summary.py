"""Summarise a DAX Studio .vpax export: model size, tables and largest columns. Usage: vpax_summary.py file.vpax"""
import json, zipfile, sys
z = zipfile.ZipFile(sys.argv[1])
v = json.loads(z.read("DaxVpaView.json").decode("utf-8-sig"))
MB = 1024*1024
T = sorted(v["Tables"], key=lambda t: -t["TableSize"])
tot = sum(t["TableSize"] for t in T)
print(f"TOTAL {tot/MB:.1f} MB")
for t in T[:12]: print(f"{t['TableName']:28} rows={t['RowsCount']:>9,} size={t['TableSize']/MB:7.2f} MB  cols={t['ColumnsSize']/MB:6.2f}")
print("\nTOP COLUMNS")
C = sorted(v["Columns"], key=lambda c: -c["TotalSize"])
for c in C[:25]: print(f"{c['FullColumnName']:50} {c['DataType']:9} {c['ColumnType']:12} {c['Encoding']:6} dict={c['DictionarySize']/MB:6.2f} data={c['DataSize']/MB:6.2f} tot={c['TotalSize']/MB:6.2f}")
print("\nREL", sum(r["UsedSize"] for r in v["Relationships"])/MB)
print("HIER", sum(h["UsedSize"] for h in v["ColumnsHierarchies"])/MB)
