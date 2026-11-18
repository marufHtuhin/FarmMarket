# Real prices, DAM, and manual daily entry

## Status: DAM is manual-entry-only — no scraper shipped

Bangladesh DAM (Department of Agricultural Marketing, dam.gov.bd) publishes
daily prices but has **no public API**. A scraper was investigated on
2026-11-17 (web search + fetched page text only, no live browser) and
**deliberately not shipped**, because the conditions for a trustworthy
scraper were not met:

1. **No verifiable table structure.** The two report pages that carry the
   daily prices — `market.dam.gov.bd/market_daily_price_report?L=E` ("Daily
   Price List Report") and `market.dam.gov.bd/subdistrict_retail_price_report?L=E`
   ("Subdistrict Wise Retail Price List Report") — return, in fetched text,
   only a heading plus instructions for downloading a PDF (enable pop-ups,
   Chrome/Firefox settings). The report table itself is rendered via
   JavaScript and/or delivered as a PDF popup, so no parseable HTML table
   could be verified from fetched content.
2. **The only machine-readable prices are a range ticker with no date.**
   Every DAM page carries a ticker line such as
   `Onion-local: 60.00 - 64.00 ▲0.00%`. It has no date, no unit and no
   market/district attribution, and the values are ranges, not single
   prices. Turning a range into FarmMarket's single `price` would require
   inventing a rule (e.g. midpoint) and guessing the market day — both
   forbidden: FarmMarket never fabricates prices.
3. **No public data access behind the summary table.** A World Bank
   reproducibility README for DAM daily price data states the underlying
   daily series is "not publicly accessible" and that data beyond the
   website's summary table must be obtained by contacting DAM directly
   (Assistant Director, Research, DAM).

Related: the DNCRP "বাজারদর (Bazardor)" Android app publishes daily
district-wise maximum retail prices, but it is an app with no public API
either, so it is not a scrape target for FarmMarket.

**Revisit only if** DAM publishes a documented API/CSV feed, or a stable,
dated, per-market HTML table can be verified in fetched content (with
timeouts, parsing guards and graceful failure, and the source attributed
on every ingested row). Do not guess DAM URLs or endpoints.

## How real prices enter FarmMarket today

An admin reads the day's DAM daily report (or another verified source) and
records it by hand:

- **API:** `POST /api/v1/prices/manual` (admin-only) with
  `{crop, hub, price, date, note}`. Stored as a `PriceObservation` with
  `source="manual"`, `is_synthetic=false`, the market day as `observed_on`,
  an entry timestamp (`ingested_at`) and the optional note (e.g. "DAM Dhaka
  retail report"). Re-entering the same hub/crop/date **updates** the stored
  price instead of duplicating it. Future dates and non-positive prices are
  rejected.
- **UI:** Admin → Data sources page ("Enter a daily price" form), with a
  list of recently entered prices below it.
- **Read:** `GET /api/v1/prices/manual` (admin-only) lists recent manual
  entries; `GET /api/v1/prices/latest` returns the latest observation per
  hub × crop for everyone.

## Labelling and staleness (never fake freshness)

Every price the API returns carries `source`, timestamps, `label`
(`"real"` | `"demo"`) and `stale`:

- `PriceObservation` labels come from `is_synthetic`. Seeded demo history
  is `is_synthetic=true` / `source="synthetic-demo"` → DEMO.
- `PriceRecord` has no `is_synthetic` column; its label is derived from the
  source string containing "demo" or "synthetic" (seeded rows carry
  `source="Illustrative demo data - replace with verified source"`).
- **Stale:** a REAL price whose observed/recorded time is more than **48
  hours** old, or a real price with no timestamp at all (freshness cannot be
  verified, so it is not claimed). Demo prices are never "stale" — the DEMO
  badge already says they are not live. A date-only observation counts from
  the start of that day (UTC), so a price observed two calendar days ago is
  stale. See `backend/app/services/price_labels.py`.
- The frontend shows a REAL (green) / DEMO (amber) badge, a red stale
  warning, the source and "updated X ago" on every price (Prices page cards
  and the "Latest prices by hub" table). A missing label is rendered as
  DEMO — the UI never claims a price is real without the backend saying so.

## What the forecasters train on

Both forecasters train on `PriceObservation` rows for one hub × crop via
`forecasting.load_series` (`backend/app/services/forecasting.py`):

- **Real data is preferred when there is enough of it.** If the
  non-synthetic rows alone form a series long enough to forecast, the
  synthetic demo rows are excluded (`series.real_only=true`,
  `synthetic_share=0`). Otherwise the full mixed series is used and the
  existing "Built on SYNTHETIC demo data" warning applies.
- **Thresholds:** the scikit-learn forecaster needs 30 points, so daily
  manual entries start driving it after ~30 days of entries. The Prophet
  forecaster needs 180 daily points, so it needs ~6 months of daily entries
  before it goes real-only. Until then, forecasts stay honest about being
  built (partly) on demo data.
- Manual entries are daily, so a real-only series has frequency `D`; the
  seeded synthetic history is weekly (`W`). Mixed series resample to a
  regular grid (mean within period, short gaps interpolated).
