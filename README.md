# Fund Static Data & Investment Operations Dashboard

Fund operations dashboard simulating middle office workflows — static data, SSI monitoring, reconciliation breaks, and trade settlement tracking. Built with Python, Supabase, and Streamlit.

Live demo: https://investment-operations-dashboard.streamlit.app/

---

## What it simulates

This dashboard simulates the internal operations tooling of a custodian bank (BNP Paribas Securities Services, Citi Securities Services) managing fund operations on behalf of external asset managers. The four tabs cover the core daily workflows of a middle office static data and reconciliation team.

---

## The four tabs

**Tab 1 — Static Data**
Reference data layer. Instruments with real prices fetched daily from Yahoo Finance via the yfinance API. Counterparties with BIC codes, LEI identifiers, and KYC status — expired KYC rows flagged red, pending flagged yellow. Settlement Instructions (SSI) per counterparty-instrument with expiry monitoring. A missing or expired SSI causes a settlement fail under CSDR rules.

**Tab 2 — Reconciliation Breaks**
Daily break register comparing internal position records against custodian records. Breaks tracked through their lifecycle: Open (red), Investigating (yellow), Resolved (green). KPI cards show open break count, total EUR exposure, and resolved today.

**Tab 3 — Trade Monitor**
Rolling 10-day trade history. Flags overdue trades in red. Flags pending trades with no active SSI in yellow. KPI cards show pending, settled, failed, and overdue counts.

**Tab 4 — Fund Overview**
One card per fund showing AUM, NAV per share, fund type (UCITS or AIF), domicile, open break count, 30-day NAV trend chart, and asset class breakdown by market value.

---

## Data

Instrument prices are real, updated daily via GitHub Actions running update_prices.py every weekday at 18:00 CET after European market close. Prices are fetched from Yahoo Finance via the yfinance API and stored in Supabase. NAV history is appended daily with realistic movements.

Funds, positions, trades, counterparties, and reconciliation breaks are synthetic data built to realistic investment operations structure.

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

Identifies where break exposure is concentrated. A disproportionate exposure in one asset class often signals a missed corporate action affecting all positions simultaneously.

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

The LEFT JOIN returning NULL on ssi_id means no active SSI exists for that counterparty-instrument pair. Without an SSI the custodian cannot generate a settlement instruction and the trade fails under CSDR.

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

Positions the fund holds where no active SSI exists for any counterparty. Cannot be sold until an SSI is set up.

---

## Automation

Daily price refresh and NAV history update runs via GitHub Actions every weekday at 18:00 CET. Workflow file at `.github/workflows/daily_prices.yml`. Runs `update_prices.py` which fetches prices from Yahoo Finance and appends one NAV row per fund to the history table.

---

## Project structure

```
investment-ops-dashboard/
├── app.py                          # Streamlit dashboard
├── seed.py                         # One-time database population
├── update_prices.py                # Daily price and NAV refresh
├── requirements.txt
├── .gitignore
├── README.md
└── .github/
    └── workflows/
        └── daily_prices.yml        # GitHub Actions schedule
```

---

## Stack

Python 3.13 | pandas | Supabase (PostgreSQL) | Streamlit | yfinance | Plotly | GitHub Actions

## AI-assisted development

Claude was used to validate the reconciliation break logic against real-world settlement scenarios, to debug the yfinance multi-ticker parsing, and to review the SSI validation SQL for edge cases (expired vs missing SSI).
