# Report: UK Ecommerce Analytics

Five pages, 1920×1080, light corporate theme (`StaticResources/RegisteredResources/UKEcomLight.json`): navy header band with the page slicers on it, white cards on a light-grey canvas, 15pt titles, 13pt labels, 30pt KPI values. Built as PBIR files in `pbip/UK_Ecommerce.Report/`, so every page and visual is a reviewable JSON file in Git.

| Page | Question it answers | Main visuals |
|---|---|---|
| **Executive Overview** | How is the business doing? | 6 KPIs · net revenue this year vs last year (calculation group) · year-to-date scorecard · revenue by region, category and marketing channel |
| **Sales & Products** | What sells, and what comes back? | 5 KPIs · units sold vs return rate by month · **Sales mix** explorer (field parameters: *Show* Net Revenue / Units / Margin % / Return Rate % / AOV, *By* Region / Sales Channel / Price Band / Age Band) · **Top 10 products** (follows the Category slicer) · return reasons |
| **Customers & Retention** | Who comes back, and who are we losing? | 5 KPIs incl. 12-month churn · **cohort retention heat-map** (cohorts Apr 2024 – Sep 2025, months 1–12) · new vs returning by month · RFM segments (count and value) |
| **Marketing & Campaigns** | Is the spend paying off? | 5 KPIs · campaign scorecard (**ROAS vs margin-based ROI**) · last-click vs acquisition-channel attribution · spend and ROAS by month · budget by channel |
| **Web Funnel** | Where do visitors drop out? | Sessions → basket → order KPIs · conversion by device over time · funnel by device · conversion by region and by marketing channel |

## Design rules
- Every chart shows **all categories combined**; the Category slicer narrows any page to one category.
- "Unknown" / "N/A" members are filtered out of every axis and slicer (they exist in the model as `-1` rows for referential integrity).
- Axis titles are off when the chart title already says what's plotted.
- Field-parameter slicers are single-select with defaults (Net Revenue × Region).

## Build and checks
- Generated programmatically (Python writing PBIR JSON).
- Validated against Microsoft's published PBIR JSON schemas (74 files, 0 errors), with every field reference, including those inside filters (172), confirmed to exist in the semantic model; theme style names checked against the official report-theme schema.
- Measures added for the funnel page: `Add to Basket Rate %`, `Basket to Order %` (folder **Web**).
