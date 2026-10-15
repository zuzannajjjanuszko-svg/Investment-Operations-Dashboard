"""Daily job for the Fund Operations Dashboard.

Real data   : instrument prices, FX rates, fund NAV (Yahoo Finance), dividends (ex-dates).
Simulated   : positions, trades, settlement instructions and reconciliation breaks.
              These are the internal records of a fund administrator and are not published,
              so they are generated from the real prices and evolve one business day at a time
              (booking, T+1 / T+2 settlement, fails, breaks and their resolution).

First run (or an empty database) bootstraps the whole universe and replays the last
BACKFILL_DAYS business days. Later runs only add the business days that are missing.
The simulation is seeded per date, so re-running the job on the same day changes nothing.
"""
import os
import random
import sys
from datetime import date, timedelta

import pandas as pd
import yfinance as yf
from supabase import create_client
from dotenv import load_dotenv

import universe as U

load_dotenv()
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

TODAY = date.today()
PAGE = 1000
CHUNK = 400
BACKFILL_DAYS = 20          # business days of trade history created on the first run
FUND_IDS = [f[0] for f in U.FUNDS]
FUND_META = {f[0]: f for f in U.FUNDS}
CCY_TICKER = {v[2]: k for k, v in U.FX.items()}
STOCK_BY_ISIN = {v[0]: k for k, v in U.STOCKS.items()}


# ── DATABASE HELPERS ─────────────────────────────────────────────────
def fetch_all(table, order, flt=None):
    """Page through a table (the API returns at most 1,000 rows per request)."""
    rows, start = [], 0
    while True:
        q = supabase.table(table).select("*")
        if flt:
            q = flt(q)
        batch = q.order(order).range(start, start + PAGE - 1).execute().data
        rows += batch
        if len(batch) < PAGE:
            return rows
        start += PAGE


def upsert(table, rows, conflict):
    for i in range(0, len(rows), CHUNK):
        supabase.table(table).upsert(rows[i:i + CHUNK], on_conflict=conflict).execute()


# ── MARKET DATA ──────────────────────────────────────────────────────
def download(period):
    tickers = list(U.STOCKS) + list(U.FX) + [f[3] for f in U.FUNDS]
    last_err = None
    for attempt in range(3):
        try:
            raw = yf.download(tickers, period=period, auto_adjust=False,
                              progress=False, threads=True)
            close = raw["Close"]
            if len(close):
                return close
        except Exception as e:           # network hiccup, retry
            last_err = e
    raise SystemExit(f"Price download failed: {last_err}")


class Prices:
    def __init__(self, close):
        close = close.copy()
        close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
        self.series = {t: close[t].dropna() for t in close.columns if close[t].notna().any()}
        stock_cols = [t for t in U.STOCKS if t in self.series]
        counts = close[stock_cols].notna().sum(axis=1) if stock_cols else pd.Series(dtype=int)
        need = 0.4 * len(U.STOCKS)
        self.trading_days = [ts.date() for ts, c in counts.items() if c >= need]

    def has(self, ticker):
        return ticker in self.series

    def raw(self, ticker, d):
        v = self.series[ticker].asof(pd.Timestamp(d))
        return None if pd.isna(v) else float(v)

    def local(self, ticker, d):
        """Price in the instrument currency (London quotes are in pence)."""
        v = self.raw(ticker, d)
        if v is None:
            return None
        return v / 100 if ticker.endswith(".L") else v

    def fx(self, ccy, d):
        """Units of ccy per 1 EUR."""
        if ccy == "EUR":
            return 1.0
        return self.raw(CCY_TICKER[ccy], d)

    def eur(self, ticker, amount_local, d):
        ccy = U.STOCKS[ticker][2]
        return amount_local / self.fx(ccy, d)

    def last_date(self):
        return self.trading_days[-1]


def add_bdays(d, n):
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


# ── STATIC DATA ──────────────────────────────────────────────────────
def instrument_rows(px, d):
    rows = []
    for tk, (isin, name, ccy, exch, ctry, _region) in U.STOCKS.items():
        if not px.has(tk):
            print(f"  WARNING no price data for {tk}")
            continue
        rows.append({"isin": isin, "sedol": None, "name": name, "asset_class": "Equity",
                     "currency": ccy, "exchange": exch, "country": ctry,
                     "price": round(px.local(tk, d), 4),
                     "price_date": str(px.series[tk].index[-1].date()), "active": True})
    for tk, (pair, name, ccy) in U.FX.items():
        if not px.has(tk):
            print(f"  WARNING no price data for {tk}")
            continue
        rows.append({"isin": pair, "sedol": None, "name": name, "asset_class": "FX",
                     "currency": ccy, "exchange": "OTC", "country": "ZZ",
                     "price": round(px.raw(tk, d), 4),
                     "price_date": str(px.series[tk].index[-1].date()), "active": True})
    return rows


def counterparty_rows():
    rng = random.Random("counterparties")
    rows = []
    for cp_id, name, bic, lei, cp_type, ctry, kyc in U.COUNTERPARTIES:
        if kyc == "Approved":
            expiry = TODAY + timedelta(days=rng.randint(120, 400))
        elif kyc == "Pending":
            expiry = TODAY + timedelta(days=30)
        else:
            expiry = TODAY - timedelta(days=45)
        rows.append({"counterparty_id": cp_id, "name": name, "bic": bic, "lei": lei,
                     "cp_type": cp_type, "country": ctry, "kyc_status": kyc,
                     "kyc_expiry": str(expiry)})
    return rows


def ssi_rows(available):
    rng = random.Random("ssi")
    rows = []
    for cp_id in U.BROKERS_ALL:
        for tk in available:
            isin, _n, ccy, _e, ctry, _r = U.STOCKS[tk]
            if cp_id == "CP10":
                status, valid_to = "Expired", str(TODAY - timedelta(days=30))
            elif cp_id == "CP08" and rng.random() < 0.4:
                status, valid_to = "Pending", None
            elif rng.random() < 0.04:
                continue                        # no instruction on file for this pair
            else:
                status, valid_to = "Active", str(TODAY + timedelta(days=365))
            rows.append({"ssi_id": f"SSI-{cp_id}-{isin}", "counterparty_id": cp_id, "isin": isin,
                         "instruction_type": "SSI", "custodian_bic": U.CSD_BIC[ctry],
                         "account_number": f"{rng.randint(10_000_000, 99_999_999)}",
                         "currency": ccy, "valid_from": "2023-01-01",
                         "valid_to": valid_to, "status": status})
    return rows


def age_static_data():
    """KYC and SSI validity run out by themselves as time passes."""
    for r in supabase.table("counterparties").select("counterparty_id,kyc_status,kyc_expiry").execute().data:
        if r["kyc_status"] == "Approved" and r["kyc_expiry"] and r["kyc_expiry"] < str(TODAY):
            supabase.table("counterparties").update({"kyc_status": "Expired"}) \
                .eq("counterparty_id", r["counterparty_id"]).execute()
    for r in fetch_all("settlement_instructions", "ssi_id", lambda q: q.eq("status", "Active")):
        if r["valid_to"] and r["valid_to"] < str(TODAY):
            supabase.table("settlement_instructions").update({"status": "Expired"}) \
                .eq("ssi_id", r["ssi_id"]).execute()


# ── FUNDS AND NAV ────────────────────────────────────────────────────
def anchor_nav(fid, ticker, px):
    row = (supabase.table("nav_history").select("nav_per_share")
           .eq("fund_id", fid).eq("nav_date", str(U.AUM_ANCHOR_DATE)).execute().data)
    if row:
        return float(row[0]["nav_per_share"])
    return px.raw(ticker, U.AUM_ANCHOR_DATE)


def update_funds_and_nav(px):
    """NAV per share is the closing price of the EUR line of each ETF (tracks NAV within a few
    basis points). AUM = issuer-reported fund size on the anchor date, scaled with NAV."""
    nav_rows, fund_rows, ok = [], [], True
    for fid, name, isin, tk, dom, inception, aum_m, _reg in U.FUNDS:
        if not px.has(tk):
            print(f"  WARNING no NAV data for {fid} ({tk})")
            ok = False
            continue
        a_nav = anchor_nav(fid, tk, px)
        s = px.series[tk]
        rows = []
        for ts, nav in s.items():
            aum = aum_m * 1e6 * float(nav) / a_nav if a_nav else aum_m * 1e6
            rows.append({"fund_id": fid, "nav_per_share": round(float(nav), 4),
                         "aum_eur": round(aum, 2), "nav_date": str(ts.date())})
        nav_rows += rows
        last = rows[-1]
        fund_rows.append({"fund_id": fid, "name": name, "isin": isin, "fund_type": "UCITS",
                          "base_currency": "EUR", "aum_eur": last["aum_eur"],
                          "nav_per_share": last["nav_per_share"], "nav_date": last["nav_date"],
                          "domicile": dom, "inception_date": inception})
    upsert("funds", fund_rows, "fund_id")
    upsert("nav_history", nav_rows, "fund_id,nav_date")
    print(f"  NAV: {len(nav_rows)} rows for {len(fund_rows)} funds.")
    return ok


def aum_on(fid, d, px):
    meta = FUND_META[fid]
    a_nav = px.raw(meta[3], U.AUM_ANCHOR_DATE) or px.raw(meta[3], d)
    return meta[6] * 1e6 * px.raw(meta[3], d) / a_nav


# ── SIMULATION ───────────────────────────────────────────────────────
class Book:
    """In-memory state of the simulated operations records."""

    def __init__(self):
        self.positions = {}      # (fund, isin) -> row
        self.trades = {}         # trade_id -> row (open trades loaded, new ones added)
        self.breaks = {}         # break_id -> row (open breaks loaded, new ones added)
        self.ssi = {}            # (cp, isin) -> row
        self.dirty_pos, self.dirty_tr, self.dirty_br = set(), set(), set()

    def touch_pos(self, key):
        self.dirty_pos.add(key)

    def touch_trade(self, tid):
        self.dirty_tr.add(tid)

    def touch_break(self, bid):
        self.dirty_br.add(bid)

    def ssi_ok(self, cp, isin, d):
        r = self.ssi.get((cp, isin))
        return bool(r and r["status"] == "Active" and (not r["valid_to"] or r["valid_to"] >= str(d)))

    def unsettled(self, fund, isin):
        """Signed quantity of booked trades that the custodian has not settled yet."""
        tot = 0.0
        for t in self.trades.values():
            if t["fund_id"] == fund and t["isin"] == isin and t["status"] in ("Pending", "Failed"):
                tot += t["quantity"] if t["trade_type"] == "Buy" else -t["quantity"]
        return tot


def load_book():
    b = Book()
    for p in fetch_all("positions", "position_id", lambda q: q.in_("fund_id", FUND_IDS)):
        b.positions[(p["fund_id"], p["isin"])] = p
    for t in fetch_all("trades", "trade_id",
                       lambda q: q.in_("fund_id", FUND_IDS).in_("status", ["Pending", "Failed"])):
        b.trades[t["trade_id"]] = t
    for r in fetch_all("reconciliation_breaks", "break_id",
                       lambda q: q.in_("fund_id", FUND_IDS).in_("status", ["Open", "Investigating"])):
        b.breaks[r["break_id"]] = r
    for r in fetch_all("settlement_instructions", "ssi_id"):
        b.ssi[(r["counterparty_id"], r["isin"])] = r
    return b


def initial_positions(px, start, available):
    """Each fund holds a sleeve of its real constituents, sized as a share of its AUM."""
    book = Book()
    for fid, *_rest in U.FUNDS:
        if not px.has(FUND_META[fid][3]):
            continue                                   # no NAV data for this fund today
        region = FUND_META[fid][7]
        allowed = sorted(tk for tk in available if U.STOCKS[tk][5] in U.UNIVERSE_REGIONS[region])
        rng = random.Random(f"positions-{fid}")
        held = rng.sample(allowed, min(U.SLEEVE_SIZE[fid], len(allowed)))
        aum = aum_on(fid, start, px)
        for tk in sorted(held):
            isin, _n, ccy, *_x = U.STOCKS[tk]
            price = px.local(tk, start)
            weight = rng.uniform(0.004, 0.03)
            qty = max(1, round(aum * weight / (price / px.fx(ccy, start))))
            book.positions[(fid, isin)] = {
                "position_id": f"POS-{fid}-{isin}", "fund_id": fid, "isin": isin,
                "internal_quantity": qty, "custodian_quantity": qty,
                "price": round(price, 4),
                "market_value_eur": round(qty * price / px.fx(ccy, start), 2),
                "position_date": str(start)}
            book.touch_pos((fid, isin))
    return book


def load_dividends(px, since):
    out = {}
    for tk in U.STOCKS:
        if not px.has(tk):
            continue
        try:
            for ts, v in yf.Ticker(tk).dividends.items():
                d = ts.date() if hasattr(ts, "date") else ts
                if d >= since:
                    out.setdefault(d, []).append((tk, float(v)))
        except Exception as e:
            print(f"  dividends unavailable for {tk}: {e}")
    return out


def trade_sign(t):
    return t["quantity"] if t["trade_type"] == "Buy" else -t["quantity"]


def open_break(book, bid, fund, isin, itype, i_qty, c_qty, b_qty, value, d):
    book.breaks[bid] = {
        "break_id": bid, "fund_id": fund, "isin": isin, "internal_qty": i_qty,
        "custodian_qty": c_qty, "break_qty": b_qty, "break_value_eur": round(value, 2),
        "break_type": itype, "status": "Open", "created_date": str(d), "resolved_date": None}
    book.touch_break(bid)


def close_break(book, bid, d):
    br = book.breaks.get(bid)
    if br and br["status"] != "Resolved":
        br["status"] = "Resolved"
        br["resolved_date"] = str(d)
        book.touch_break(bid)


def simulate_day(d, book, px, dividends):
    rng = random.Random(f"sim-{d.isoformat()}")
    sk = lambda isin: STOCK_BY_ISIN[isin]
    funds = sorted({f for (f, _isin) in book.positions})

    # 1. settlement processing of trades that fall due today or earlier
    for tid in sorted(book.trades):
        t = book.trades[tid]
        if t["status"] == "Pending" and t["settlement_date"] <= str(d):
            key = (t["fund_id"], t["isin"])
            pos = book.positions[key]
            fails = (not book.ssi_ok(t["counterparty_id"], t["isin"], d)) or rng.random() < 0.025
            if fails:
                t["status"] = "Failed"
                book.touch_trade(tid)
                tk = sk(t["isin"])
                value = px.eur(tk, t["quantity"] * px.local(tk, d), d)
                open_break(book, f"BRK-{tid}", t["fund_id"], t["isin"], "Missing",
                           pos["internal_quantity"], pos["custodian_quantity"],
                           t["quantity"], value, d)
            else:
                t["status"] = "Settled"
                pos["custodian_quantity"] += trade_sign(t)
                book.touch_trade(tid)
                book.touch_pos(key)
        elif t["status"] == "Failed":
            key = (t["fund_id"], t["isin"])
            pos = book.positions[key]
            ssi_ok = book.ssi_ok(t["counterparty_id"], t["isin"], d)
            age = (d - date.fromisoformat(t["settlement_date"])).days
            if age >= 10:                                # buy-in / cancellation
                t["status"] = "Cancelled"
                pos["internal_quantity"] -= trade_sign(t)
                book.touch_trade(tid)
                book.touch_pos(key)
                close_break(book, f"BRK-{tid}", d)
            elif age >= 1 and rng.random() < (0.40 if ssi_ok else 0.08):
                t["status"] = "Settled"
                pos["custodian_quantity"] += trade_sign(t)
                book.touch_trade(tid)
                book.touch_pos(key)
                close_break(book, f"BRK-{tid}", d)

    # 2. new trades booked today
    for fid in funds:
        held = sorted(isin for (f, isin) in book.positions if f == fid)
        for k in range(rng.choices([1, 2, 3, 4], [0.3, 0.4, 0.2, 0.1])[0]):
            isin = rng.choice(held)
            pos = book.positions[(fid, isin)]
            tk = sk(isin)
            ctry = U.STOCKS[tk][4]
            side = "Buy" if rng.random() < 0.55 else "Sell"
            qty = max(1, round(pos["internal_quantity"] * rng.uniform(0.01, 0.06)))
            if side == "Sell":
                qty = min(qty, int(pos["internal_quantity"] * 0.3))
                if qty < 1:
                    side = "Buy"
                    qty = 1
            cp = rng.choice(U.BROKERS_ACTIVE) if rng.random() < 0.94 else rng.choice(["CP08", "CP10"])
            price = round(px.local(tk, d) * (1 + rng.gauss(0, 0.0008)), 4)
            sd = add_bdays(d, U.SETTLEMENT_CYCLE.get(ctry, U.DEFAULT_CYCLE))
            tid = f"T-{d:%Y%m%d}-{fid}-{k + 1:02d}"
            cancelled = rng.random() < 0.01
            row = {"trade_id": tid, "fund_id": fid, "isin": isin, "trade_type": side,
                   "quantity": qty, "price": price, "trade_date": str(d),
                   "settlement_date": str(sd), "status": "Cancelled" if cancelled else "Pending",
                   "counterparty_id": cp, "ssi_id": f"SSI-{cp}-{isin}"}
            book.trades[tid] = row
            book.touch_trade(tid)
            if not cancelled:
                pos["internal_quantity"] += trade_sign(row)
                book.touch_pos((fid, isin))

    # 3. new reconciliation breaks from operational errors
    for (fid, isin) in sorted(book.positions):
        pos = book.positions[(fid, isin)]
        tk = sk(isin)
        ccy = U.STOCKS[tk][2]
        price = px.local(tk, d)
        has_open_qty = any(b["fund_id"] == fid and b["isin"] == isin and b["break_type"] == "Quantity"
                           and b["status"] != "Resolved" for b in book.breaks.values())
        if not has_open_qty and rng.random() < 0.02:
            delta = max(1, round(pos["internal_quantity"] * rng.uniform(0.001, 0.01)))
            delta = delta if rng.random() < 0.5 else -delta
            pos["custodian_quantity"] += delta
            book.touch_pos((fid, isin))
            open_break(book, f"BRK-Q-{d:%Y%m%d}-{fid}-{isin}", fid, isin, "Quantity",
                       pos["internal_quantity"], pos["custodian_quantity"], abs(delta),
                       abs(delta) * price / px.fx(ccy, d), d)
        if rng.random() < 0.012:
            pct = rng.uniform(0.002, 0.025)
            q = pos["internal_quantity"]
            open_break(book, f"BRK-P-{d:%Y%m%d}-{fid}-{isin}", fid, isin, "Price", q, q, 0,
                       q * price * pct / px.fx(ccy, d), d)
    for tk, dps in dividends.get(d, []):
        isin = U.STOCKS[tk][0]
        raw_close = px.raw(tk, d)
        ratio = dps / raw_close if raw_close else 0
        if not 0.0005 < ratio < 0.10:
            continue                                     # unit mismatch or data error
        ccy = U.STOCKS[tk][2]
        for fid in funds:
            pos = book.positions.get((fid, isin))
            if pos and rng.random() < 0.25:
                q = pos["internal_quantity"]
                open_break(book, f"BRK-CA-{d:%Y%m%d}-{fid}-{isin}", fid, isin, "Corporate Action",
                           q, q, 0, ratio * q * px.local(tk, d) / px.fx(ccy, d), d)

    # 4. break lifecycle: Open -> Investigating -> Resolved
    for bid in sorted(book.breaks):
        br = book.breaks[bid]
        if br["status"] == "Resolved" or br["created_date"] == str(d):
            continue
        age = (d - date.fromisoformat(br["created_date"])).days
        if br["status"] == "Open" and rng.random() < 0.6:
            br["status"] = "Investigating"
            book.touch_break(bid)
        elif br["status"] == "Investigating" and not bid.startswith("BRK-T-"):
            if rng.random() < min(0.95, 0.20 + 0.07 * age) or age >= 12:
                br["status"] = "Resolved"
                br["resolved_date"] = str(d)
                book.touch_break(bid)
                if br["break_type"] == "Quantity":        # custodian record corrected
                    key = (br["fund_id"], br["isin"])
                    pos = book.positions[key]
                    pos["custodian_quantity"] = pos["internal_quantity"] - book.unsettled(*key)
                    book.touch_pos(key)

    # 5. positions as of today
    for key in sorted(book.positions):
        book.positions[key]["position_date"] = str(d)
        book.touch_pos(key)


def revalue_positions(book, px, d):
    for key, pos in book.positions.items():
        tk = STOCK_BY_ISIN[pos["isin"]]
        price = px.local(tk, d)
        if price is None:
            continue
        pos["price"] = round(price, 4)
        pos["market_value_eur"] = round(pos["internal_quantity"] * price / px.fx(U.STOCKS[tk][2], d), 2)
        book.touch_pos(key)


def flush(book):
    pos_rows = [book.positions[k] for k in sorted(book.dirty_pos)]
    for r in pos_rows:
        r["internal_quantity"] = int(r["internal_quantity"])
        r["custodian_quantity"] = int(r["custodian_quantity"])
    upsert("positions", pos_rows, "position_id")
    upsert("trades", [book.trades[k] for k in sorted(book.dirty_tr)], "trade_id")
    upsert("reconciliation_breaks", [book.breaks[k] for k in sorted(book.dirty_br)], "break_id")
    print(f"  wrote {len(pos_rows)} positions, {len(book.dirty_tr)} trades, {len(book.dirty_br)} breaks.")


# ── MAIN ─────────────────────────────────────────────────────────────
def main():
    has_pos = supabase.table("positions").select("position_id").in_("fund_id", FUND_IDS).limit(1).execute().data
    boot = not has_pos                  # also redoes a bootstrap that was interrupted before positions were written
    print(f"{TODAY}: {'bootstrap' if boot else 'daily update'}")

    px = Prices(download("2y" if boot else "1mo"))
    if not px.trading_days:
        raise SystemExit("No usable price history returned.")
    last = px.last_date()
    available = [tk for tk in U.STOCKS
                 if px.has(tk) and (U.STOCKS[tk][2] == "EUR" or px.has(CCY_TICKER[U.STOCKS[tk][2]]))]
    missing = [tk for tk in list(U.STOCKS) + list(U.FX) + [f[3] for f in U.FUNDS] if not px.has(tk)]
    print(f"  prices for {len(available)}/{len(U.STOCKS)} stocks, last trading day {last}; missing: {missing or 'none'}")
    if len(missing) > 0.25 * (len(U.STOCKS) + len(U.FX) + len(U.FUNDS)):
        raise SystemExit("Too many tickers without data, aborting before writing anything.")

    if boot:
        print("Bootstrapping static data...")
        upsert("counterparties", counterparty_rows(), "counterparty_id")
        upsert("instruments", instrument_rows(px, last), "isin")
        upsert("settlement_instructions", ssi_rows(available), "ssi_id")
        nav_ok = update_funds_and_nav(px)
        start = px.trading_days[max(0, len(px.trading_days) - 1 - BACKFILL_DAYS)]
        book = initial_positions(px, start, available)
        # make the new SSIs visible to the simulation
        for r in supabase.table("settlement_instructions").select("*").execute().data:
            book.ssi[(r["counterparty_id"], r["isin"])] = r
        last_done = start
    else:
        print("Refreshing prices...")
        upsert("instruments", instrument_rows(px, last), "isin")
        age_static_data()
        nav_ok = update_funds_and_nav(px)
        book = load_book()
        last_done = max((date.fromisoformat(p["position_date"]) for p in book.positions.values()),
                        default=None)
        if last_done is None:
            raise SystemExit("No positions found for the funds.")

    days = [d for d in px.trading_days if last_done < d <= last]
    print(f"Simulating {len(days)} business day(s)...")
    if days:
        dividends = load_dividends(px, days[0])
        for d in days:
            simulate_day(d, book, px, dividends)
    revalue_positions(book, px, last)
    flush(book)

    print("Done.")
    if not nav_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
