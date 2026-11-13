# Synthetic sales contract / lineage

## Events
Required fields: `event_id` (UUID), `event_time_utc` (ISO 8601 UTC), `channel` (`store`/`ecommerce`), `store_id`, `region`, `product_category`, `quantity` (>0), `unit_price_usd` (nonnegative decimal), `order_status` (`completed`/`refunded`), `schema_version`, `producer_run_id`.

- Synthetic only. Never add customer names, emails, phone numbers, addresses, payment cards or real order information.
- Include deliberately invalid fixture rows; quarantine/report failures. Deduplicate `event_id` before aggregates. Specify refund semantics and currency precision in the Phase 3 implementation design.
- Bronze contains captured Avro and capture metadata; Silver contains valid normalized Parquet and auditable reject counts. Gold aggregates are queryable by report window, region, channel, category, run ID and as-of timestamp.

## Serving and AI

- `dbo.sales_kpi_hourly` keyed by reporting window/region/channel, including revenue/order count/AOV/`gold_run_id`/`as_of_utc`.
- `dbo.pipeline_run_status` includes `gold_run_id`, source/accepted/rejected counts, last event/freshness and load status. Re-runs must be idempotent.
- The AI summary must read an **actual** SQL snapshot and output a generated report and validation evidence including query window, run ID, freshness, rejected rows and checks of numerical claims.
- Never invent observed volumes, SLOs, scan costs or success before a real run.
