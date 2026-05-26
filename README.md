# Fund Static Data & Investment Operations Dashboard

A simulation of the daily operational workflow in a fund services middle office:
static data management, position reconciliation, trade settlement monitoring,
and fund NAV overview.

Built with Python, pandas, Supabase (PostgreSQL), and Streamlit.
Live demo: https://investment-operations-dashboard.streamlit.app/

---

## What it does

**Tab 1 — Static Data**
Instruments, counterparties, and settlement instructions (SSI). Monitors SSI
expiry status and flags counterparties with expired or pending KYC. SSI expiry
is the leading operational cause of settlement fails in European equities markets.

**Tab 2 — Reconciliation Breaks**
Daily break register comparing internal position records against custodian records.
Breaks classified by type (Quantity / Price / Missing / Corporate Action) and tracked
through their lifecycle (Open / Investigating / Resolved). KPI cards show total open
exposure in EUR.

**Tab 3 — Trade Monitor**
Rolling 10-day trade history. Flags overdue trades and pending trades with no active
SSI on file. A pending trade with a missing SSI will fail on settlement date under
CSDR rules, triggering mandatory buy-in procedures.

**Tab 4 — Fund Overview**
AUM, NAV per share, fund type (UCITS/AIF), domicile, and asset class breakdown by
market value for each of the five funds in the database.

---

## SQL Queries

### 1. Open reconciliation breaks by fund and asset class

```sql
SELECT f.name AS fund_name, i.asset_class,
       COUNT(*) AS open_breaks,
       SUM(b.break_value_eur) AS total_exposure_eur
FROM reconciliation_breaks b
JOIN funds f ON b.fund_id = f.fund_id
JOIN instruments i ON b.isin = i.isin
WHERE b.status = 'Open'
GROUP BY f.name, i.asset_class
ORDER BY total_exposure_eur DESC;
```

Identifies where break exposure is concentrated. A disproportionate exposure in one
asset class often signals a missed corporate action affecting all positions simultaneously.

### 2. Pending trades with no active SSI

```sql
SELECT t.trade_id, t.isin, t.settlement_date,
       t.counterparty_id, t.status AS trade_status,
       si.status AS ssi_status
FROM trades t
LEFT JOIN settlement_instructions si
  ON t.counterparty_id = si.counterparty_id
  AND t.isin = si.isin
  AND si.instruction_type = 'SSI'
  AND si.status = 'Active'
WHERE t.status = 'Pending'
  AND si.ssi_id IS NULL
ORDER BY t.settlement_date;
```

The LEFT JOIN returning NULL on ssi_id means no active SSI exists for that
counterparty-instrument pair. Without an SSI the custodian cannot generate a
settlement instruction and the trade fails under CSDR.

### 3. Positions held with no active SSI on file

```sql
SELECT p.fund_id, p.isin, i.name, i.asset_class,
       p.internal_quantity, p.market_value_eur
FROM positions p
JOIN instruments i ON p.isin = i.isin
WHERE NOT EXISTS (
  SELECT 1 FROM settlement_instructions si
  WHERE si.isin = p.isin AND si.status = 'Active'
)
AND p.position_date = CURRENT_DATE
ORDER BY p.market_value_eur DESC;
```

Positions the fund holds where no active SSI exists for any counterparty.
Cannot be sold until an SSI is set up. Proactive identification prevents
last-minute settlement fails when the PM decides to exit.

---

## Data

Instrument prices are real, fetched from Yahoo Finance via yfinance.
Funds, positions, trades, and reconciliation breaks are synthetic data
built to realistic investment operations structure.

## Stack

Python 3.13 | pandas | Supabase (PostgreSQL) | Streamlit | yfinance

## AI-assisted development

Claude was used to validate the reconciliation break logic against real-world
settlement scenarios, to debug the yfinance multi-ticker parsing, and to review
the SSI validation SQL for edge cases (expired vs missing SSI).
