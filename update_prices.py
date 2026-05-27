import os
import random
import sys
from datetime import date, timedelta

import yfinance as yf
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

TODAY = date.today()

TICKERS = {
    "MC.PA":    "FR0000121014",
    "ASML":     "NL0010273215",
    "NESN.SW":  "CH0012221716",
    "SAN.PA":   "FR0000120578",
    "SIE.DE":   "DE0007236101",
    "BNP.PA":   "FR0000131104",
    "IBGL.L":   "IE00B14X4T88",
    "IEGA.L":   "IE00B4WXJJ64",
    "DBXE.DE":  "LU0321463258",
    "CSH2.PA":  "FR0010149120",
    "XEON.DE":  "LU0290358497",
    "EXX5.DE":  "DE0002635307",
    "EURUSD=X": "XS0000000001",
    "EURGBP=X": "XS0000000002",
    "EURPLN=X": "XS0000000003",
}


def update_prices():
    print(f"Fetching prices for {TODAY}...")
    tickers = list(TICKERS.keys())
    data = yf.download(tickers, period="5d", auto_adjust=True, progress=False)["Close"]
    updated = 0
    failed = 0
    for ticker, isin in TICKERS.items():
        try:
            price = round(float(data[ticker].dropna().iloc[-1]), 4)
            price_date = str(data[ticker].dropna().index[-1].date())
            supabase.table("instruments").update({
                "price": price,
                "price_date": price_date,
            }).eq("isin", isin).execute()
            updated += 1
        except Exception as e:
            print(f"  Failed {ticker}: {e}")
            failed += 1
    print(f"  {updated} prices updated, {failed} failed.")


def append_nav_today():
    print("Appending NAV for today...")
    funds = supabase.table("funds").select("fund_id,nav_per_share,aum_eur").execute().data
    for fund in funds:
        move = 1 + random.uniform(-0.015, 0.015)
        new_nav = round(fund["nav_per_share"] * move, 4)
        new_aum = round(fund["aum_eur"] * move, 2)
        supabase.table("funds").update({
            "nav_per_share": new_nav,
            "aum_eur": new_aum,
            "nav_date": str(TODAY),
        }).eq("fund_id", fund["fund_id"]).execute()
        supabase.table("nav_history").upsert({
            "fund_id": fund["fund_id"],
            "nav_per_share": new_nav,
            "aum_eur": new_aum,
            "nav_date": str(TODAY),
        }, on_conflict="fund_id,nav_date").execute()
    print(f"  NAV updated for {len(funds)} funds.")


def backfill_nav(days=30):
    print(f"Backfilling {days} days of NAV history...")
    funds = supabase.table("funds").select("fund_id,nav_per_share,aum_eur").execute().data
    for fund in funds:
        nav = fund["nav_per_share"]
        aum = fund["aum_eur"]
        for i in range(days, 0, -1):
            d = TODAY - timedelta(days=i)
            if d.weekday() >= 5:
                continue
            move = 1 + random.uniform(-0.015, 0.015)
            nav = round(nav * move, 4)
            aum = round(aum * move, 2)
            supabase.table("nav_history").upsert({
                "fund_id": fund["fund_id"],
                "nav_per_share": nav,
                "aum_eur": aum,
                "nav_date": str(d),
            }, on_conflict="fund_id,nav_date").execute()
    print(f"  Backfill complete for {len(funds)} funds.")


if __name__ == "__main__":
    if "--backfill" in sys.argv:
        backfill_nav(30)
    else:
        update_prices()
        append_nav_today()
    print("Done.")