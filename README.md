# Fund Static Data & Investment Operations Dashboard

Operations dashboard simulating the daily middle office workflow at a global fund servicer: instrument, counterparty and settlement instruction (SSI) static data, reconciliation break tracking, trade settlement monitoring, and NAV and AUM for five international UCITS ETFs. An AI Assistant answers plain-English questions on the live data. Built with Python, SQL, Supabase, Streamlit and Gemini.

Live demo: https://investment-operations-dashboard.streamlit.app/

---

## What it simulates

The internal operations tooling of a fund servicer or custodian managing fund operations on behalf of external asset managers. The five tabs cover the core daily workflows of a middle office static data and reconciliation team.

---

## The five tabs

**Tab 1 - Static Data**
Reference data layer. 29 international equities (US, Europe, Japan) and 5 FX rates with real prices fetched daily from Yahoo Finance. Counterparties with BIC codes, LEI identifiers (checked against the GLEIF register) and KYC status, with expired KYC flagged red and pending flagged yellow. Settlement Instructions (SSI) per counterparty-instrument pair, with the place of settlement (central securities depository) of each market and expiry monitoring. A missing or expired SSI causes a settlement fail under CSDR rules.

**Tab 2 - Reconciliation Breaks**
Daily break register comparing internal position records against custodian records. Breaks are tracked through their lifecycle: Open (red), Investigating (yellow), Resolved (green). Types: Quantity, Price, Missing (a failed settlement) and Corporate Action (a dividend entitlement not booked). KPI cards show open break count, total EUR exposure and resolved today.

**Tab 3 - Trade Monitor**
Rolling two-week trade history. Flags failed and overdue trades in red and trades with no active SSI in yellow. KPI cards show pending, settled, failed and overdue counts.

**Tab 4 - Fund Overview**
One card per fund showing AUM, NAV per share, fund type, domicile, open break count and exposure, 30-day NAV trend and the country breakdown of the monitored holdings.

**Tab 5 - AI Assistant**
Ask a question about the current state of the data in plain English (for example "Which fund has the most open reconciliation breaks?"). The current funds, instruments, counterparties, SSIs, trades and breaks are passed to Gemini as context. Answers are cached per question and the free-tier rate limit is handled with a short wait message.

---

## Data

**Real**
- The five funds are real UCITS ETFs: iShares Core MSCI World, Vanguard FTSE All-World, iShares Core S&P 500, iShares STOXX Europe 600 (DE) and iShares Core MSCI Europe. ISIN, name, domicile and inception date are the published ones.
- Instrument prices, FX rates and fund NAV come from Yahoo Finance and are refreshed every weekday after the European close. NAV per share is the closing price of each ETF's EUR line, which tracks the published NAV within a few basis points. Full NAV history for two years is loaded.
- AUM is the fund size reported on the anchor date (15 Oct 2026), scaled with NAV on other dates (shares outstanding held constant).
- Counterparties are real institutions; their LEIs are checked against the GLEIF register.
- Dividend ex-dates come from Yahoo Finance and drive the Corporate Action breaks.

**Simulated** (these are internal records of a fund administrator and are not published anywhere)
- Positions: a sleeve of each fund's real constituents, sized as a share of AUM and revalued daily with the real prices.
- Trades: booked every business day at the real closing price, with the standard settlement cycle of each market (T+1 for the US, T+2 for Europe, the UK, Switzerland and Japan). A trade fails when no active SSI exists for the counterparty and instrument pair, or at random (about 2.5 percent). Failed trades are retried and cancelled after ten days.
- Reconciliation breaks: custodian quantity moves at settlement while the internal book moves at trade date, so unsettled trades are explained differences. Breaks are created for failed settlements, quantity errors, price differences and unbooked dividends, and move from Open to Investigating to Resolved with realistic ageing.
- Settlement instructions and the KYC status of the counterparties.

The simulation is seeded per date, so rerunning the job on the same day changes nothing.

---

## SQL Queries

### 1. Open reconciliation breaks by fund and country of issuer

```sql
SELECT f.name AS fund_name, i.country,
       COUNT(*) AS open_breaks,
       SUM(b.break_value_eur) AS total_exposure_eur
FROM reconciliation_breaks b
JOIN funds f ON b.fund_id = f.fund_id
JOIN instruments i ON b.isin = i.isin
WHERE b.status IN ('Open', 'Investigating')
GROUP BY f.name, i.country
ORDER BY total_exposure_eur DESC;
```

Identifies where break exposure is concentrated. A disproportionate exposure in one market often points to a settlement depot problem or a missed corporate action affecting all positions in that market.

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
SELECT p.fund_id, p.isin, i.name, i.country,
       p.internal_quantity, p.market_value_eur
FROM positions p
JOIN instruments i ON p.isin = i.isin
WHERE NOT EXISTS (
  SELECT 1 FROM settlement_instructions si
  WHERE si.isin = p.isin AND si.status = 'Active'
)
AND p.position_date = (SELECT MAX(position_date) FROM positions)
ORDER BY p.market_value_eur DESC;
```

Positions a fund holds where no active SSI exists for any counterparty. They cannot be sold until an SSI is set up.

### 4. Unexplained position differences (internal vs custodian)

```sql
SELECT p.fund_id, p.isin,
       p.internal_quantity - p.custodian_quantity AS difference,
       COALESCE(SUM(CASE WHEN t.trade_type = 'Buy' THEN t.quantity ELSE -t.quantity END), 0) AS unsettled_trades
FROM positions p
LEFT JOIN trades t
  ON t.fund_id = p.fund_id AND t.isin = p.isin
  AND t.status IN ('Pending', 'Failed')
GROUP BY p.fund_id, p.isin, p.internal_quantity, p.custodian_quantity
HAVING p.internal_quantity - p.custodian_quantity
     <> COALESCE(SUM(CASE WHEN t.trade_type = 'Buy' THEN t.quantity ELSE -t.quantity END), 0);
```

The internal book moves at trade date and the custodian at settlement date, so unsettled trades explain part of the gap. What remains is a real break to investigate.

---

## Automation

A GitHub Actions workflow (`.github/workflows/daily_prices.yml`) runs `update_prices.py` every weekday at 18:00 CET. The job downloads prices, FX rates and NAV, updates the instruments and funds, lets KYC and SSI validity expire, and then advances the simulated operations records by the business days that are missing. The first run creates the whole universe and replays the last 20 business days.

---

## Project structure

```
Investment-Operations-Dashboard/
├── app.py                          # Streamlit dashboard
├── universe.py                     # Funds, instruments, counterparties and market conventions
├── update_prices.py                # Daily market data refresh and operations simulation
├── requirements.txt
├── .gitignore
├── README.md
└── .github/
    └── workflows/
        └── daily_prices.yml        # GitHub Actions schedule
```

---

## Stack

Python 3.13 | pandas | Supabase (PostgreSQL) | Streamlit | yfinance | Plotly | Gemini | GitHub Actions

## AI-assisted development

Claude was used to validate the reconciliation break logic against real-world settlement scenarios, to debug the yfinance multi-ticker parsing, and to review the SSI validation SQL for edge cases (expired vs missing SSI).
