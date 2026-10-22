# Data Dictionary

How to read it: **RAW** describes what the source systems send (the generator's output contract). **MARTS** describes what Power BI sees. STAGING sits between them and is documented in its SQL (Day 5).

Every RAW table also has two load-audit columns: `_loaded_at` (TIMESTAMP_NTZ, when COPY INTO ran) and `_source_file` (VARCHAR, the Parquet file name).

---

## RAW layer (source contract)

The column types are as delivered. Source systems are messy, so some columns arrive as text and are cast in STAGING.

### raw.customers (CRM)
| Column | Type | Description |
|---|---|---|
| customer_id | INT | Unique customer ID |
| email | VARCHAR | Login email (may be NULL for guest-converted accounts) |
| first_name, last_name | VARCHAR | Synthetic names |
| postcode | VARCHAR | Full UK postcode as typed by the customer |
| registered_at | VARCHAR | Account creation timestamp |
| date_of_birth | DATE | Optional |
| marketing_opt_in | BOOLEAN | Email marketing consent |

### raw.products (PIM)
| Column | Type | Description |
|---|---|---|
| product_id | INT | Unique product ID |
| sku | VARCHAR | Stock code, e.g. `P-10421` |
| product_name | VARCHAR | |
| category | VARCHAR | Home, Fashion, Electronics, Beauty, Books, Kids |
| subcategory | VARCHAR | |
| brand | VARCHAR | |
| list_price | NUMBER(10,2) | Current selling price, inc. VAT |
| unit_cost | NUMBER(10,2) | Current cost price, ex. VAT |
| vat_rate | NUMBER(4,2) | 0.20 or 0.00 |
| launched_on | DATE | |
| discontinued_on | DATE | NULL if still on sale |

### raw.orders (OMS)
| Column | Type | Description |
|---|---|---|
| order_id | INT | Unique order ID |
| customer_id | INT | |
| order_ts | VARCHAR | Order timestamp |
| sales_channel | VARCHAR | `web`, `app` or `marketplace` |
| session_id | VARCHAR | The session the order was placed in (NULL for marketplace) |
| delivery_postcode | VARCHAR | |
| promo_code | VARCHAR | NULL if none |
| shipping_fee | NUMBER(10,2) | Inc. VAT |
| payment_method | VARCHAR | card, paypal, klarna, apple_pay; `marketplace` when the marketplace took payment |
| status | VARCHAR | Completed or Cancelled |

### raw.order_lines (OMS)
| Column | Type | Description |
|---|---|---|
| order_line_id | INT | Unique line ID |
| order_id | INT | |
| product_id | INT | |
| quantity | INT | |
| unit_price | NUMBER(10,2) | Price charged, inc. VAT |
| discount_amount | NUMBER(10,2) | Total line discount, inc. VAT |
| unit_cost | NUMBER(10,2) | Cost at time of order, ex. VAT |

### raw.returns (returns portal)
| Column | Type | Description |
|---|---|---|
| return_id | INT | |
| order_line_id | INT | |
| return_date | DATE | Date the item was received back |
| quantity_returned | INT | |
| reason_code | VARCHAR | e.g. `SIZE`, `FAULTY`, `NOT_AS_DESC`, `CHANGED_MIND`, `LATE` |
| refund_amount | NUMBER(10,2) | Inc. VAT |

### raw.sessions (web/app analytics)
| Column | Type | Description |
|---|---|---|
| session_id | VARCHAR | Unique session ID |
| session_start_ts | TIMESTAMP_NTZ | |
| customer_id | INT | NULL if the visitor wasn't logged in |
| device | VARCHAR | desktop, mobile_web, ios_app, android_app |
| channel | VARCHAR | Traffic source (see dim_channel) |
| campaign_code | VARCHAR | utm_campaign, NULL if none |
| landing_page_type | VARCHAR | home, category, product, search, promo |
| postcode_area | VARCHAR | IP-derived area (approximate) |
| pageviews | INT | |
| added_to_basket | BOOLEAN | |
| converted | BOOLEAN | Placed an order in this session |

### raw.campaigns (marketing calendar)
| Column | Type | Description |
|---|---|---|
| campaign_id | INT | |
| campaign_code | VARCHAR | Matches `sessions.campaign_code` and `orders.promo_code` |
| campaign_name | VARCHAR | |
| campaign_type | VARCHAR | Seasonal sale, Product launch, Retention, Brand |
| start_date, end_date | DATE | |
| discount_pct | NUMBER(4,2) | Headline discount, 0 if none |

### raw.marketing_spend (ad platforms)
| Column | Type | Description |
|---|---|---|
| spend_date | DATE | |
| campaign_code | VARCHAR | NULL = always-on (non-campaign) spend |
| channel | VARCHAR | |
| spend | NUMBER(12,2) | GBP ex. VAT |
| impressions | INT | |
| clicks | INT | |

### raw.postcode_areas (reference)
| Column | Type | Description |
|---|---|---|
| postcode_area | VARCHAR | 1–2 letters, e.g. `M`, `BT`, `EH` |
| area_name | VARCHAR | e.g. Manchester, Belfast, Edinburgh |
| region | VARCHAR | ITL1 region, e.g. North West |
| country | VARCHAR | England, Scotland, Wales, Northern Ireland |

---

## MARTS layer (what Power BI sees)

All money columns are GBP. "ex-VAT" means VAT has been removed.

### fact_order_line
| Column | Type | Description / rule |
|---|---|---|
| order_line_key | INT | = order_line_id |
| order_id | INT | Degenerate dimension (no dim_order) |
| order_date_key | INT | YYYYMMDD |
| order_ts | TIMESTAMP_NTZ | Kept for incremental refresh (RangeStart/RangeEnd) |
| customer_key | INT | → dim_customer |
| product_key | INT | → dim_product (-1 if the product isn't in the PIM) |
| geography_key | INT | → dim_geography, from the delivery postcode |
| channel_key | INT | → dim_channel, last non-direct click |
| campaign_key | INT | → dim_campaign, last non-direct click (-1 if none) |
| sales_channel | VARCHAR | web / app / marketplace |
| is_cancelled | INT | 1 = cancelled order (exclude from measures) |
| quantity | INT | |
| gross_sales | NUMBER | quantity × unit_price, inc. VAT |
| discount_amount | NUMBER | inc. VAT |
| net_revenue | NUMBER | (gross_sales − discount) ÷ (1 + vat_rate) |
| vat_amount | NUMBER | (gross_sales − discount) − net_revenue |
| cogs | NUMBER | quantity × unit_cost |
| gross_margin | NUMBER | net_revenue − cogs |
| shipping_allocated | NUMBER | Order shipping (ex-VAT) × line share of order net revenue |

### fact_returns
| Column | Type | Description / rule |
|---|---|---|
| return_key | INT | = return_id |
| order_line_key | INT | → fact_order_line (kept for drill-through) |
| return_date_key | INT | YYYYMMDD |
| order_date_key | INT | Order date of the original line (return rate is by order date) |
| customer_key | INT | |
| product_key | INT | |
| return_reason_key | INT | → dim_return_reason |
| quantity_returned | INT | |
| refund_amount | NUMBER | ex-VAT |

### fact_sessions
| Column | Type | Description / rule |
|---|---|---|
| session_id | VARCHAR | Degenerate |
| session_date_key | INT | YYYYMMDD |
| session_start_ts | TIMESTAMP_NTZ | For incremental refresh |
| customer_key | INT | -1 = anonymous |
| channel_key | INT | |
| campaign_key | INT | -1 = no campaign |
| geography_key | INT | From IP-derived postcode area |
| device | VARCHAR | |
| landing_page_type | VARCHAR | |
| pageviews | INT | |
| added_to_basket | INT | 0/1 (integers sum well in DAX) |
| converted | INT | 0/1 |

### fact_marketing_spend
| Column | Type | Description |
|---|---|---|
| spend_date_key | INT | |
| campaign_key | INT | -1 = always-on |
| channel_key | INT | |
| spend | NUMBER | ex-VAT |
| impressions | INT | |
| clicks | INT | |

### dim_date
`date_key` (INT, YYYYMMDD), `date`, `day_of_week`, `day_name`, `is_weekend`, `week_start_date` (Monday), `month_start_date`, `month_name`, `month_number`, `year`, `quarter`, `fiscal_year` (e.g. `FY2025`), `fiscal_quarter`, `fiscal_month_number` (April = 1), `is_uk_bank_holiday`.

### dim_customer
| Column | Description |
|---|---|
| customer_key | = customer_id; -1 = Anonymous |
| customer_name | |
| geography_key | Home postcode area |
| registered_date | |
| first_order_date | First completed order |
| cohort_month | First day of the first-order month (used by the cohort matrix). NULL for Pre-2023 customers |
| cohort_label | `YYYY-MM`, or `Pre-2023` for customers registered before the data starts |
| acquisition_channel | Channel of the first order (last non-direct click) |
| age_band | 18–24, 25–34, … , Unknown |
| marketing_opt_in | |
| is_test_account | 1 = internal/test (filtered out in MARTS facts) |

### dim_product
`product_key`, `sku`, `product_name`, `category`, `subcategory`, `brand`, `list_price`, `unit_cost`, `vat_rate`, `price_band` (Under £20, £20–49, £50–99, £100+), `launched_on`, `is_active`. Row -1 = "Unknown product".

### dim_geography
`geography_key`, `postcode_area`, `area_name`, `region`, `country`. Row -1 = "Unknown".

### dim_channel
`channel_key`, `channel_name`, `channel_group` (Paid / Owned / Earned / Direct / Marketplace), `is_paid`.

### dim_campaign
`campaign_key`, `campaign_code`, `campaign_name`, `campaign_type`, `start_date`, `end_date`, `discount_pct`. Row -1 = "No campaign".

### dim_return_reason
`return_reason_key`, `reason_code`, `reason_description`, `is_controllable` (1 for reasons the business can fix: FAULTY, NOT_AS_DESC, LATE).

### security_user_region
`user_principal_name` (Entra login), `region` (or `ALL`).
