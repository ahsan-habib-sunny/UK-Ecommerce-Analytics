"""Day 11 report, v2: bigger type, navy header band, no 'Unknown', all-category views, Top 10 products,
business-focused sales mix explorer. Run from the repo root. Rewrites all report pages and the theme."""
import json, pathlib, shutil, uuid

REPORT = pathlib.Path("pbip/UK_Ecommerce.Report")
DEF = REPORT / "definition"
W, H = 1920, 1080
M, GAP = 24, 16
BAND_H = 104                      # navy header band
TOP = BAND_H + M                  # first content row
KPI_H = 128
NAVY, BLUE, INK, MUTED = "#1F4E79", "#4A90C2", "#000000", "#000000"
THEME_NAME = "UKEcomLight.json"
SCHEMA_VC = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.13.0/schema.json"

# ------------------------------------------------------------------ fields
def col(e, p): return {"Column": {"Expression": {"SourceRef": {"Entity": e}}, "Property": p}}
def mea(p, e="_Measures"): return {"Measure": {"Expression": {"SourceRef": {"Entity": e}}, "Property": p}}
def proj(f):
    k = "Measure" if "Measure" in f else "Column"
    e, p = f[k]["Expression"]["SourceRef"]["Entity"], f[k]["Property"]
    return {"field": f, "queryRef": f"{e}.{p}", "nativeQueryRef": p}
def lit(v): return {"expr": {"Literal": {"Value": v}}}
def s(t): return lit("'" + t.replace("'", "''") + "'")
def color(c): return {"solid": {"color": s(c)}}
def vid(): return uuid.uuid4().hex[:20]

# ------------------------------------------------------------------ filters
def _src(prop): return {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}}

def f_in(entity, prop, values, negate=False, literal=lambda v: "'" + v + "'"):
    cond = {"In": {"Expressions": [_src(prop)], "Values": [[{"Literal": {"Value": literal(v)}}] for v in values]}}
    if negate:
        cond = {"Not": {"Expression": cond}}
    return {"name": vid(), "field": col(entity, prop), "type": "Categorical",
            "filter": {"Version": 2, "From": [{"Name": "t", "Entity": entity, "Type": 0}], "Where": [{"Condition": cond}]}}

def f_not_unknown(entity, prop, values=("Unknown",)):
    return f_in(entity, prop, list(values), negate=True)

def f_topn(entity, prop, measure, n):
    return {"name": vid(), "field": col(entity, prop), "type": "TopN", "filter": {
        "Version": 2,
        "From": [
            {"Name": "subquery", "Type": 2, "Expression": {"Subquery": {"Query": {
                "Version": 2,
                "From": [{"Name": "d", "Entity": entity, "Type": 0}, {"Name": "m", "Entity": "_Measures", "Type": 0}],
                "Select": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": prop}, "Name": "field"}],
                "OrderBy": [{"Direction": 2, "Expression": {"Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": measure}}}],
                "Top": n}}}},
            {"Name": "d", "Entity": entity, "Type": 0}],
        "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": prop}}],
                                        "Table": {"SourceRef": {"Source": "subquery"}}}}}]}}

NOT_UNKNOWN = {
    ("dim_geography", "REGION"): lambda: f_not_unknown("dim_geography", "REGION"),
    ("dim_product", "CATEGORY"): lambda: f_not_unknown("dim_product", "CATEGORY"),
    ("dim_channel", "CHANNEL_NAME"): lambda: f_not_unknown("dim_channel", "CHANNEL_NAME"),
    ("dim_return_reason", "REASON_DESCRIPTION"): lambda: f_not_unknown("dim_return_reason", "REASON_DESCRIPTION"),
}

# ------------------------------------------------------------------ visuals
def container(x, y, w, h, visual, filters=None):
    out = {"$schema": SCHEMA_VC, "name": vid(),
           "position": {"x": round(x, 2), "y": round(y, 2), "z": 0, "height": round(h, 2), "width": round(w, 2), "tabOrder": 0},
           "visual": visual}
    if filters:
        out["filterConfig"] = {"filters": filters}
    return out

BAR_TYPES = {"clusteredBarChart", "clusteredColumnChart", "barChart", "columnChart", "lineClusteredColumnComboChart"}

def chart(vtype, x, y, w, h, roles, title, sort=None, filters=None, objects=None):
    v = {"visualType": vtype,
         "query": {"queryState": {r: {"projections": [proj(f) for f in fs]} for r, fs in roles.items()}}}
    if sort:
        v["query"]["sortDefinition"] = {"sort": [{"field": sort[0], "direction": sort[1]}], "isDefaultSort": False}
    objects = dict(objects or {})
    if vtype in BAR_TYPES and "labels" not in objects:      # data labels on every bar / column chart
        objects["labels"] = [{"properties": {"show": lit("true"), "fontSize": lit("13D"), "color": color(INK)}}]
    if objects:
        v["objects"] = objects
    v["visualContainerObjects"] = {"title": [{"properties": {"show": lit("true"), "text": s(title)}}]}
    v["drillFilterOtherVisuals"] = True
    # automatically hide 'Unknown' members of any dimension used on an axis / rows
    auto = [NOT_UNKNOWN[(f["Column"]["Expression"]["SourceRef"]["Entity"], f["Column"]["Property"])]()
            for fs in roles.values() for f in fs
            if "Column" in f and (f["Column"]["Expression"]["SourceRef"]["Entity"], f["Column"]["Property"]) in NOT_UNKNOWN]
    return container(x, y, w, h, v, (filters or []) + auto)

def card(x, y, w, h, measure):
    v = {"visualType": "card", "query": {"queryState": {"Values": {"projections": [proj(mea(measure))]}}},
         "visualContainerObjects": {"title": [{"properties": {"show": lit("false")}}]},
         "drillFilterOtherVisuals": True}
    return container(x, y, w, h, v)

def slicer(x, y, w, h, field, header, single=False, default=None, filters=None):
    objs = {"data": [{"properties": {"mode": s("Dropdown")}}],
            "header": [{"properties": {"text": s(header), "fontColor": color(INK)}}]}
    if single:
        objs["selection"] = [{"properties": {"singleSelect": lit("true")}}]
    if default:
        ent, prop = field["Column"]["Expression"]["SourceRef"]["Entity"], field["Column"]["Property"]
        objs["general"] = [{"properties": {"filter": {"filter": {
            "Version": 2, "From": [{"Name": "p", "Entity": ent, "Type": 0}],
            "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "p"}}, "Property": prop}}],
                                            "Values": [[{"Literal": {"Value": "'" + default + "'"}}]]}}}]}}}}]
    v = {"visualType": "slicer", "query": {"queryState": {"Values": {"projections": [proj(field)]}}},
         "objects": objs, "visualContainerObjects": {"title": [{"properties": {"show": lit("false")}}]},
         "drillFilterOtherVisuals": True}
    key = (field["Column"]["Expression"]["SourceRef"]["Entity"], field["Column"]["Property"])
    auto = [NOT_UNKNOWN[key]()] if key in NOT_UNKNOWN else []
    return container(x, y, w, h, v, (filters or []) + auto)

def header_band(title, subtitle, slicers):
    paras = [{"textRuns": [{"value": title, "textStyle": {"fontWeight": "bold", "fontSize": "26pt", "color": "#FFFFFF"}}]}]
    band = container(0, 0, W, BAND_H, {
        "visualType": "textbox",
        "objects": {"general": [{"properties": {"paragraphs": paras}}]},
        "visualContainerObjects": {
            "background": [{"properties": {"show": lit("true"), "color": color(NAVY), "transparency": lit("0D")}}],
            "border": [{"properties": {"show": lit("false")}}],
            "padding": [{"properties": {"top": lit("26D"), "left": lit("28D")}}]},
        "drillFilterOtherVisuals": True})
    out = [band]
    sw = 250
    for i, (field, label) in enumerate(slicers):
        x = W - M - (len(slicers) - i) * (sw + GAP) + GAP
        out.append(slicer(x, 18, sw, BAND_H - 36, field, label))
    return out

def row(y, h, n, x0=M, width=W - 2 * M):
    w = (width - GAP * (n - 1)) / n
    return [(x0 + i * (w + GAP), y, w, h) for i in range(n)]

def kpis(names):
    return [card(x, y, w, h, m_) for (x, y, w, h), m_ in zip(row(TOP, KPI_H, len(names)), names)]

YEAR = (col("dim_date", "YEAR"), "Year")
REGION = (col("dim_geography", "REGION"), "Region")
CATEGORY = (col("dim_product", "CATEGORY"), "Category")
CHANNEL = (col("dim_channel", "CHANNEL_NAME"), "Marketing channel")
DEVICE = (col("fact_sessions", "DEVICE"), "Device")
MONTH = col("dim_date", "MONTH_START_DATE")
TI = col("Time Intelligence", "Time Calculation")
Y2 = TOP + KPI_H + GAP            # second row
SUB = "Jan 2023 – Sep 2026  ·  revenue is net of discounts and excludes VAT"

# ------------------------------------------------------------------ pages
def page_overview():
    vs = header_band("Executive Overview", SUB, [YEAR, REGION, CATEGORY])
    vs += kpis(["Net Revenue", "Margin %", "Orders", "AOV", "Customers", "Conversion Rate %"])
    h2 = 410
    vs.append(chart("lineChart", M, Y2, 1240, h2,
                    {"Category": [MONTH], "Y": [mea("Net Revenue")], "Series": [TI]},
                    "Net revenue: this year vs last year (PY)",
                    filters=[f_in("Time Intelligence", "Time Calculation", ["Current", "PY"])]))
    vs.append(chart("pivotTable", M + 1240 + GAP, Y2, W - 2 * M - 1240 - GAP, h2,
                    {"Rows": [col("dim_date", "YEAR")], "Columns": [TI], "Values": [mea("Net Revenue")]},
                    "Year-to-date scorecard",
                    objects={
                        "columnHeaders": [{"properties": {"columnAdjustment": s("growToFit"), "fontSize": lit("18D"),
                                                          "alignment": s("Center")}}],
                        "rowHeaders": [{"properties": {"fontSize": lit("20D"), "bold": lit("true")}}],
                        "values": [{"properties": {"fontSize": lit("20D")}}],
                        "grid": [{"properties": {"rowPadding": lit("22D")}}],
                        "subTotals": [{"properties": {"rowSubtotals": lit("false"), "columnSubtotals": lit("false")}}]},
                    filters=[f_in("Time Intelligence", "Time Calculation", ["YTD", "PY YTD", "YoY %"])]))
    y3 = Y2 + h2 + GAP
    a, b, c = row(y3, H - y3 - M, 3)
    vs.append(chart("clusteredBarChart", *a, {"Category": [col("dim_geography", "REGION")], "Y": [mea("Net Revenue")]},
                    "Revenue by region", sort=(mea("Net Revenue"), "Descending")))
    vs.append(chart("clusteredBarChart", *b, {"Category": [col("dim_product", "CATEGORY")], "Y": [mea("Net Revenue")]},
                    "Revenue by category", sort=(mea("Net Revenue"), "Descending")))
    vs.append(chart("clusteredBarChart", *c, {"Category": [col("dim_channel", "CHANNEL_NAME")], "Y": [mea("Net Revenue")]},
                    "Revenue by marketing channel", sort=(mea("Net Revenue"), "Descending")))
    return "Executive Overview", vs


def page_sales():
    vs = header_band("Sales & Products", "All categories by default. Use the Category slicer to focus on one",
                     [YEAR, REGION, CATEGORY])
    vs += kpis(["Net Revenue", "Gross Margin", "Margin %", "Units Sold", "Return Rate %"])
    h2 = 410
    vs.append(chart("lineClusteredColumnComboChart", M, Y2, 1100, h2,
                    {"Category": [MONTH], "Y": [mea("Units Sold")], "Y2": [mea("Return Rate %")]},
                    "Units sold and return rate by month"))
    # Sales mix explorer (field parameters, single-select, sensible defaults)
    xe, we = M + 1100 + GAP, W - 2 * M - 1100 - GAP
    vs.append(slicer(xe, Y2, (we - GAP) / 2, 76, col("Metric Selector", "Metric Selector"), "Show",
                     single=True, default="Net Revenue"))
    vs.append(slicer(xe + (we + GAP) / 2, Y2, (we - GAP) / 2, 76, col("Dimension Selector", "Dimension Selector"), "By",
                     single=True, default="Region"))
    explorer = chart("clusteredBarChart", xe, Y2 + 76 + GAP, we, h2 - 76 - GAP,
                     {"Category": [col("dim_geography", "REGION")], "Y": [mea("Net Revenue")]},
                     "Sales mix: choose what to show and how to split it",
                     filters=[f_not_unknown("dim_product", "CATEGORY")])
    qs = explorer["visual"]["query"]["queryState"]
    qs["Category"]["fieldParameters"] = [{"parameterExpr": col("Dimension Selector", "Dimension Selector"), "index": 0, "length": 1}]
    qs["Y"]["fieldParameters"] = [{"parameterExpr": col("Metric Selector", "Metric Selector"), "index": 0, "length": 1,
                                   "sortDirection": "Descending"}]
    explorer["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"] = {"expr": mea("Sales Mix Title")}
    explorer["visual"]["objects"] = {"labels": [{"properties": {"show": lit("true"), "fontSize": lit("13D"),
                                                                 "color": color(INK)}}]}
    vs.append(explorer)
    y3 = Y2 + h2 + GAP
    h3 = H - y3 - M
    vs.append(chart("tableEx", M, y3, 1100, h3,
                    {"Values": [col("dim_product", "PRODUCT_NAME"), col("dim_product", "CATEGORY"),
                                mea("Net Revenue"), mea("Units Sold"), mea("Margin %"), mea("Return Rate %")]},
                    "Top 10 products by net revenue",
                    sort=(mea("Net Revenue"), "Descending"),
                    filters=[f_topn("dim_product", "SKU", "Net Revenue", 10)]))
    vs.append(chart("clusteredBarChart", M + 1100 + GAP, y3, W - 2 * M - 1100 - GAP, h3,
                    {"Category": [col("dim_return_reason", "REASON_DESCRIPTION")], "Y": [mea("Units Returned")]},
                    "Why products come back", sort=(mea("Units Returned"), "Descending")))
    return "Sales & Products", vs


COHORTS = [f"{y}-{m:02d}" for y in (2024, 2025) for m in range(1, 13)][3:21]   # 2024-04 … 2025-09

def page_customers():
    vs = header_band("Customers & Retention", "Who buys, who comes back, and who we're losing", [YEAR, REGION])
    vs += kpis(["Customers", "New Customers", "Repeat Customer Rate %", "Active Customers (12M)", "Churn Rate % (12M)"])
    h2 = 470
    heat = {"values": [{"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {
                "Input": mea("Retention %"),
                "FillRule": {"linearGradient2": {
                    "min": {"color": {"Literal": {"Value": "'#FFFFFF'"}}, "value": {"Literal": {"Value": "0D"}}},
                    "max": {"color": {"Literal": {"Value": "'#4A90C2'"}}, "value": {"Literal": {"Value": "0.15D"}}},
                    "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}}}}}}}}}},
                "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": "_Measures.Retention %"}}],
            "subTotals": [{"properties": {"rowSubtotals": lit("false"), "columnSubtotals": lit("false")}}]}
    vs.append(chart("pivotTable", M, Y2, 1120, h2,
                    {"Rows": [col("dim_customer", "COHORT_LABEL")], "Columns": [col("Cohort Offset", "Month Offset")],
                     "Values": [mea("Retention %")]},
                    "Retention by first-purchase month: % buying again 1–12 months later",
                    objects=heat,
                    filters=[f_in("Cohort Offset", "Month Offset", [str(i) for i in range(1, 13)], literal=lambda v: v + "L"),
                             f_in("dim_customer", "COHORT_LABEL", COHORTS)]))
    vs.append(chart("columnChart", M + 1120 + GAP, Y2, W - 2 * M - 1120 - GAP, h2,
                    {"Category": [MONTH], "Y": [mea("New Customers"), mea("Returning Customers")]},
                    "New vs returning customers by month"))
    y3 = Y2 + h2 + GAP
    a, b = row(y3, H - y3 - M, 2)
    no_inactive = [f_in("Customer RFM", "RFM Segment", ["Inactive (no order in 12M)"], negate=True)]
    vs.append(chart("clusteredBarChart", *a, {"Category": [col("Customer RFM", "RFM Segment")], "Y": [mea("RFM Customers")]},
                    "Customer segments (RFM, last 12 months)", filters=no_inactive))
    vs.append(chart("tableEx", *b,
                    {"Values": [col("Customer RFM", "RFM Segment"), mea("RFM Customers"), mea("RFM Revenue 12M"),
                                mea("RFM Revenue Share %")]},
                    "Value of each segment", filters=no_inactive))
    return "Customers & Retention", vs


def page_marketing():
    vs = header_band("Marketing & Campaigns", "Is the spend paying off? Revenue credited to the last non-direct click",
                     [YEAR, CHANNEL])
    vs += kpis(["Marketing Spend", "Net Revenue", "ROAS", "Campaign ROI %", "Cost per New Customer"])
    h2 = 450
    vs.append(chart("tableEx", M, Y2, 1180, h2,
                    {"Values": [col("dim_campaign", "CAMPAIGN_NAME"), col("dim_campaign", "START_DATE"),
                                mea("Net Revenue"), mea("Marketing Spend"), mea("ROAS"), mea("Campaign ROI %")]},
                    "Campaign scorecard: ROAS looks at revenue, ROI at profit",
                    sort=(col("dim_campaign", "START_DATE"), "Descending"),
                    filters=[f_in("dim_campaign", "CAMPAIGN_CODE", ["NONE"], negate=True)]))
    vs.append(chart("clusteredBarChart", M + 1180 + GAP, Y2, W - 2 * M - 1180 - GAP, h2,
                    {"Category": [col("dim_channel", "CHANNEL_NAME")],
                     "Y": [mea("Net Revenue"), mea("Net Revenue (Acquisition Channel)")]},
                    "Who closes the sale vs who brings the customer",
                    sort=(mea("Net Revenue"), "Descending")))
    y3 = Y2 + h2 + GAP
    a, b = row(y3, H - y3 - M, 2)
    vs.append(chart("lineClusteredColumnComboChart", *a,
                    {"Category": [MONTH], "Y": [mea("Marketing Spend")], "Y2": [mea("ROAS")]},
                    "Monthly spend and return on ad spend"))
    vs.append(chart("clusteredBarChart", *b, {"Category": [col("dim_channel", "CHANNEL_NAME")], "Y": [mea("Marketing Spend")]},
                    "Where the budget goes", sort=(mea("Marketing Spend"), "Descending")))
    return "Marketing & Campaigns", vs


def page_funnel():
    vs = header_band("Web Funnel", "Website and app visits → basket → order", [YEAR, REGION, DEVICE])
    vs += kpis(["Sessions", "Add to Basket Rate %", "Basket to Order %", "Conversion Rate %"])
    h2 = 450
    vs.append(chart("lineChart", M, Y2, 1240, h2,
                    {"Category": [MONTH], "Y": [mea("Conversion Rate %")], "Series": [col("fact_sessions", "DEVICE")]},
                    "Conversion rate by device"))
    vs.append(chart("pivotTable", M + 1240 + GAP, Y2, W - 2 * M - 1240 - GAP, h2,
                    {"Rows": [col("fact_sessions", "DEVICE")],
                     "Values": [mea("Sessions"), mea("Add to Basket Rate %"), mea("Basket to Order %")]},
                    "Funnel by device"))
    y3 = Y2 + h2 + GAP
    a, b = row(y3, H - y3 - M, 2)
    vs.append(chart("clusteredBarChart", *a, {"Category": [col("dim_geography", "REGION")], "Y": [mea("Conversion Rate %")]},
                    "Conversion rate by region", sort=(mea("Conversion Rate %"), "Descending")))
    vs.append(chart("lineClusteredColumnComboChart", *b,
                    {"Category": [col("dim_channel", "CHANNEL_NAME")], "Y": [mea("Sessions")], "Y2": [mea("Conversion Rate %")]},
                    "Traffic and conversion by marketing channel", sort=(mea("Sessions"), "Descending")))
    return "Web Funnel", vs

# ------------------------------------------------------------------ theme (sizes per user: ~14–15pt)
THEME = {
    "name": "UK Ecommerce Light",
    "dataColors": [NAVY, "#2E86AB", "#F18F01", "#C73E1D", "#5BA585", "#6C757D", "#8E6BBF", "#E3B23C",
                   "#3D5A80", "#98C1D9", "#EE6C4D", "#293241"],
    "background": "#FFFFFF", "foreground": INK, "tableAccent": NAVY,
    "good": "#2E7D32", "neutral": "#F9A825", "bad": "#C62828",
    "maximum": NAVY, "center": "#98C1D9", "minimum": "#FFFFFF",
    "textClasses": {
        "callout": {"fontFace": "Segoe UI Semibold", "fontSize": 30, "color": INK},
        "title": {"fontFace": "Segoe UI Semibold", "fontSize": 15, "color": INK},
        "header": {"fontFace": "Segoe UI Semibold", "fontSize": 14, "color": INK},
        "label": {"fontFace": "Segoe UI", "fontSize": 13, "color": INK},
    },
    "visualStyles": {
        "*": {"*": {
            "background": [{"show": True, "color": {"solid": {"color": "#FFFFFF"}}, "transparency": 0}],
            "border": [{"show": True, "color": {"solid": {"color": "#E5E7EB"}}, "radius": 10}],
            "dropShadow": [{"show": True, "color": {"solid": {"color": "#000000"}}, "transparency": 92, "position": "Outer",
                            "preset": "Custom", "shadowSpread": 0, "shadowBlur": 10, "angle": 90, "shadowDistance": 2}],
            "title": [{"show": True, "fontColor": {"solid": {"color": INK}}, "fontSize": 15, "fontFamily": "Segoe UI Semibold"}],
            "padding": [{"top": 10, "bottom": 10, "left": 14, "right": 14}],
            "categoryAxis": [{"fontSize": 13, "showAxisTitle": False, "labelColor": {"solid": {"color": INK}}}],
            "valueAxis": [{"fontSize": 13, "showAxisTitle": False, "labelColor": {"solid": {"color": INK}},
                           "gridlineColor": {"solid": {"color": "#EEF1F5"}}}],
            "legend": [{"fontSize": 13, "showTitle": False, "position": "Top", "labelColor": {"solid": {"color": INK}}}],
            "labels": [{"fontSize": 13, "color": {"solid": {"color": INK}}}],
            "subTitle": [{"show": False}],
        }},
        "page": {"*": {
            "background": [{"color": {"solid": {"color": "#F3F5F8"}}, "transparency": 0}],
            "outspace": [{"color": {"solid": {"color": "#F3F5F8"}}, "transparency": 0}],
        }},
        "card": {"*": {
            "labels": [{"fontSize": 30, "color": {"solid": {"color": INK}}}],
            "categoryLabels": [{"fontSize": 14, "color": {"solid": {"color": MUTED}}}],
        }},
        "tableEx": {"*": {
            "columnHeaders": [{"fontSize": 13, "fontColor": {"solid": {"color": "#FFFFFF"}}, "backColor": {"solid": {"color": NAVY}}}],
            "values": [{"fontSize": 13, "fontColor": {"solid": {"color": INK}}}], "total": [{"fontSize": 13, "fontColor": {"solid": {"color": INK}}}],
        }},
        "pivotTable": {"*": {
            "columnHeaders": [{"fontSize": 13, "fontColor": {"solid": {"color": "#FFFFFF"}}, "backColor": {"solid": {"color": NAVY}}}],
            "rowHeaders": [{"fontSize": 13, "fontColor": {"solid": {"color": INK}}}], "values": [{"fontSize": 13, "fontColor": {"solid": {"color": INK}}}],
            "total": [{"fontSize": 13, "fontColor": {"solid": {"color": INK}}}],
        }},
        "slicer": {"*": {
            "header": [{"textSize": 13, "fontColor": {"solid": {"color": INK}}}], "items": [{"textSize": 13, "fontColor": {"solid": {"color": INK}}}],
            "border": [{"show": False}], "dropShadow": [{"show": False}],
        }},
        "textbox": {"*": {"dropShadow": [{"show": False}]}},
    },
}


def main():
    res = REPORT / "StaticResources" / "RegisteredResources"
    res.mkdir(parents=True, exist_ok=True)
    (res / THEME_NAME).write_text(json.dumps(THEME, indent=2), encoding="utf-8")
    pages_dir = DEF / "pages"
    for child in pages_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
    order = []
    for build in (page_overview, page_sales, page_customers, page_marketing, page_funnel):
        display, visuals = build()
        pid = vid()
        order.append(pid)
        pdir = pages_dir / pid
        (pdir / "visuals").mkdir(parents=True)
        (pdir / "page.json").write_text(json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
            "name": pid, "displayName": display, "displayOption": "FitToPage", "height": H, "width": W}, indent=2),
            encoding="utf-8")
        for i, v in enumerate(visuals):
            v["position"]["z"] = i
            v["position"]["tabOrder"] = i
            (pdir / "visuals" / v["name"]).mkdir()
            (pdir / "visuals" / v["name"] / "visual.json").write_text(json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{display:<24}{len(visuals):>3} visuals")
    (pages_dir / "pages.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
        "pageOrder": order, "activePageName": order[0]}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
