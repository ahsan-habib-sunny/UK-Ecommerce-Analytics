"""Summarise a Performance Analyzer JSON export: per-visual median timings and per-page query totals. Run from the repo root. Usage: perf_summary.py file.json"""
import json, sys, collections, datetime, pathlib, glob, statistics as st
d = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8-sig")); ev = d["events"]
vis = {}
for p in glob.glob("pbip/UK_Ecommerce.Report/definition/pages/*/visuals/*/visual.json"):
    j = json.load(open(p, encoding="utf-8")); pg = json.load(open(pathlib.Path(p).parents[2]/"page.json", encoding="utf-8"))
    t = j.get("visual",{}).get("visualContainerObjects",{}).get("title",[{}])[0].get("properties",{}).get("text",{}).get("expr",{}).get("Literal",{}).get("Value","")
    vis[j["name"]] = (pg["displayName"], j.get("visual",{}).get("visualType",""), t.strip("'"))
ts = lambda s: datetime.datetime.fromisoformat(s.replace("Z","+00:00"))
dur = lambda e: (ts(e["end"]) - ts(e["start"])).total_seconds()*1000
kids = collections.defaultdict(list)
for e in ev: kids[e.get("parentId")].append(e)
def desc(e):
    for k in kids[e["id"]]:
        yield k; yield from desc(k)
runs = collections.defaultdict(list)
for e in ev:
    if e["name"] == "Visual Container Lifecycle" and "end" in e:
        vid = e.get("metrics",{}).get("visualId")
        dax = sum(dur(k) for k in desc(e) if k["name"] == "Execute DAX Query" and "end" in k)
        ren = sum(dur(k) for k in desc(e) if k["name"] == "Render" and "end" in k)
        runs[vid].append((dur(e), dax, ren))
print("runs per visual:", collections.Counter(len(r) for r in runs.values()))
rows = []
for vid, r in runs.items():
    rows.append((st.median(x[0] for x in r), max(x[1] for x in r), st.median(x[1] for x in r), st.median(x[2] for x in r), vid))
rows.sort(key=lambda x: -x[1])
print("TOP by DAX (max ms) | median total | median dax | median render")
for tot, dmax, dmed, ren, vid in rows[:15]:
    pg, vt, t = vis.get(vid, ("?","?","?"))
    print(f"dax_max={dmax:6.0f} tot={tot:6.0f} dax={dmed:5.0f} render={ren:5.0f}  {pg[:20]:20} {vt[:17]:17} {t[:44]}")
pages = collections.defaultdict(list)
for tot, dmax, dmed, ren, vid in rows: pages[vis.get(vid,("?",))[0]].append((dmed, tot))
print()
for p, v in pages.items(): print(f"{p:24} visuals={len(v):2} sum_dax={sum(x[0] for x in v):6.0f} max_total={max(x[1] for x in v):6.0f}")
