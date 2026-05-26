import os
import random
import uuid
from datetime import date, timedelta

import pandas as pd
import yfinance as yf
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

TODAY = date.today()


def uid():
    return str(uuid.uuid4())[:8]


# ── INSTRUMENT DEFINITIONS ───────────────────────────────────────────
# ticker -> (ISIN, SEDOL, name, asset_class, currency, exchange, country)
INSTRUMENTS = {
    "MC.PA":    ("FR0000121014","B3KNMY3","LVMH Moet Hennessy",      "Equity",     "EUR","Euronext Paris",    "FR"),
    "ASML":     ("NL0010273215","BDRXN07","ASML Holding",            "Equity",     "EUR","Euronext Amsterdam","NL"),
    "NESN.SW":  ("CH0012221716","7159696","Nestle SA",               "Equity",     "CHF","SIX Swiss Exchange","CH"),
    "SAN.PA":   ("FR0000120578","B035C36","Sanofi SA",               "Equity",     "EUR","Euronext Paris",    "FR"),
    "SIE.DE":   ("DE0007236101","5529207","Siemens AG",              "Equity",     "EUR","Xetra",             "DE"),
    "BNP.PA":   ("FR0000131104","4849507","BNP Paribas SA",          "Equity",     "EUR","Euronext Paris",    "FR"),
    "IBGL.L":   ("IE00B14X4T88","B14X4T8","iShares EUR Govt Bond",   "Bond",       "EUR","LSE",               "IE"),
    "IEGA.L":   ("IE00B4WXJJ64","B4WXJJ6","iShares Core EUR Govt",   "Bond",       "EUR","LSE",               "IE"),
    "DBXE.DE":  ("LU0321463258","B2Y9G50","Xtrackers EUR Corp Bond", "Bond",       "EUR","Xetra",             "DE"),
    "EURUSD=X": ("XS0000000001","0000001","EUR/USD Spot",            "FX",         "USD","OTC",               "ZZ"),
    "EURGBP=X": ("XS0000000002","0000002","EUR/GBP Spot",            "FX",         "GBP","OTC",               "ZZ"),
    "EURPLN=X": ("XS0000000003","0000003","EUR/PLN Spot",            "FX",         "PLN","OTC",               "ZZ"),
    "CSH2.PA":  ("FR0010149120","7174437","Lyxor Smart Cash ETF",    "MoneyMarket","EUR","Euronext Paris",    "FR"),
    "XEON.DE":  ("LU0290358497","B1CNZS6","Xtrackers EUR Overnight", "MoneyMarket","EUR","Xetra",             "DE"),
    "EXX5.DE":  ("DE0002635307","2635307","iShares DAX ETF",         "Equity",     "EUR","Xetra",             "DE"),
}

FUNDS = [
    ("F001","Horizon European Equity Fund","LU0000000101","UCITS","EUR",450_000_000,105.42,"LU"),
    ("F002","Alpha Fixed Income AIF",      "LU0000000102","AIF",  "EUR",820_000_000, 98.17,"LU"),
    ("F003","Core Money Market UCITS",     "IE0000000103","UCITS","EUR",210_000_000,100.01,"IE"),
    ("F004","Multi-Asset Growth Fund",     "LU0000000104","UCITS","EUR",175_000_000,122.88,"LU"),
    ("F005","Global Equity AIF",           "IE0000000105","AIF",  "USD",630_000_000, 87.34,"IE"),
]

COUNTERPARTIES = [
    ("CP01","Goldman Sachs International","GSILGB2LXXX","549300JXZN6HJHJJ4S28","Broker",   "GB","Approved"),
    ("CP02","Societe Generale SA",        "SOGEFRPPXXX","O2RNE8IBXP4R0TD8PH29","Broker",   "FR","Approved"),
    ("CP03","Deutsche Bank AG",           "DEUTDEDBXXX","7LTWFZYICNSX8D621K86","Broker",   "DE","Approved"),
    ("CP04","Euroclear Bank",             "MGTCBEBEXXX","A5GWLFH3KM7YV2SFQL84","Custodian","BE","Approved"),
    ("CP05","BNP Paribas Securities Svc", "PARBFRPPXXX","R0MUWSFPU8MPRO8K5P83","Custodian","FR","Approved"),
    ("CP06","LCH SA",                     "LCHSFRPPXXX","222100BYQA4MHQ2CI919","CCP",      "FR","Approved"),
    ("CP07","Barclays Bank PLC",          "BARCGB22XXX","G5GSEF7VJP5I7OUK5573","Broker",   "GB","Approved"),
    ("CP08","Credit Agricole CIB",        "BSUIFRPPXXX","1VUV7VQFKUOQSJ21A208","Broker",   "FR","Pending"),
    ("CP09","ABN AMRO Bank NV",           "ABNANL2AXXX","BFXS5XCR2JDEANWOFM57","Broker",   "NL","Approved"),
    ("CP10","Raiffeisen Bank Intl",       "RZBAATWWXXX","9ZHRYM6F437SQJ6OUG95","Broker",   "AT","Expired"),
]


def fetch_prices():
    print("  Downloading prices from Yahoo Finance...")
    tickers = list(INSTRUMENTS.keys())
    data = yf.download(tickers, period="5d", auto_adjust=True, progress=False)["Close"]
    rows = []
    for ticker, meta in INSTRUMENTS.items():
        isin, sedol, name, asset_class, currency, exchange, country = meta
        try:
            price      = float(data[ticker].dropna().iloc[-1])
            price_date = str(data[ticker].dropna().index[-1].date())
        except Exception:
            price, price_date = 100.0, str(TODAY)
        rows.append({
            "isin": isin, "sedol": sedol, "name": name,
            "asset_class": asset_class, "currency": currency,
            "exchange": exchange, "country": country,
            "price": round(price, 4), "price_date": price_date,
            "active": True,
        })
    return rows


def insert_instruments(instruments):
    for inst in instruments:
        supabase.table("instruments").upsert(inst).execute()


def insert_funds():
    for f in FUNDS:
        supabase.table("funds").upsert({
            "fund_id": f[0], "name": f[1], "isin": f[2], "fund_type": f[3],
            "base_currency": f[4], "aum_eur": f[5], "nav_per_share": f[6],
            "nav_date": str(TODAY), "domicile": f[7], "inception_date": "2018-01-15",
        }).execute()


def insert_counterparties():
    for cp in COUNTERPARTIES:
        supabase.table("counterparties").upsert({
            "counterparty_id": cp[0], "name": cp[1], "bic": cp[2], "lei": cp[3],
            "cp_type": cp[4], "country": cp[5], "kyc_status": cp[6],
            "kyc_expiry": str(TODAY + timedelta(days=90)),
        }).execute()


def insert_ssis(instruments):
    broker_ids = ["CP01","CP02","CP03","CP07","CP08","CP09","CP10"]
    tradeable  = [i for i in instruments if i["asset_class"] in ("Equity","Bond")]
    records = []
    for cp_id in broker_ids:
        for inst in tradeable:
            isin = inst["isin"]
            if cp_id == "CP10":
                status, valid_to = "Expired", str(TODAY - timedelta(days=30))
            elif cp_id == "CP08" and random.random() < 0.4:
                status, valid_to = "Pending", None
            elif random.random() < 0.08:
                continue
            else:
                status, valid_to = "Active", str(TODAY + timedelta(days=365))
            records.append({
                "ssi_id":           f"SSI-{cp_id}-{isin[-6:]}",
                "counterparty_id":  cp_id,
                "isin":             isin,
                "instruction_type": "SSI",
                "custodian_bic":    "PARBFRPPXXX",
                "account_number":   f"ACC{random.randint(10000,99999)}",
                "currency":         "EUR",
                "valid_from":       "2023-01-01",
                "valid_to":         valid_to,
                "status":           status,
            })
    for r in records:
        supabase.table("settlement_instructions").upsert(r).execute()


def insert_positions(instruments):
    fund_ids = [f[0] for f in FUNDS]
    for fund_id in fund_ids:
        held = random.sample(instruments, random.randint(8, 12))
        for inst in held:
            iq = round(random.uniform(1000, 50000), 0)
            cq = iq + random.choice([-200,-100,-50,50,100,200]) if random.random() < 0.15 else iq
            supabase.table("positions").upsert({
                "position_id":        uid(),
                "fund_id":            fund_id,
                "isin":               inst["isin"],
                "internal_quantity":  iq,
                "custodian_quantity": cq,
                "price":              inst["price"],
                "market_value_eur":   round(iq * inst["price"], 2),
                "position_date":      str(TODAY),
            }).execute()


def insert_trades(instruments):
    fund_ids  = [f[0] for f in FUNDS]
    brokers   = ["CP01","CP02","CP03","CP07","CP09"]
    tradeable = [i for i in instruments if i["asset_class"] in ("Equity","Bond")]
    for _ in range(80):
        inst    = random.choice(tradeable)
        fund_id = random.choice(fund_ids)
        cp_id   = random.choice(brokers)
        td      = TODAY - timedelta(days=random.randint(0, 9))
        sd      = td + timedelta(days=2)
        status  = ("Failed"  if random.random() < 0.10 else
                   "Settled" if sd < TODAY else "Pending")
        supabase.table("trades").upsert({
            "trade_id":        f"T-{uid()}",
            "fund_id":         fund_id,
            "isin":            inst["isin"],
            "trade_type":      random.choice(["Buy","Sell"]),
            "quantity":        round(random.uniform(500, 10000), 0),
            "price":           inst["price"],
            "trade_date":      str(td),
            "settlement_date": str(sd),
            "status":          status,
            "counterparty_id": cp_id,
            "ssi_id":          f"SSI-{cp_id}-{inst['isin'][-6:]}",
        }).execute()


def insert_breaks(instruments):
    fund_ids    = [f[0] for f in FUNDS]
    tradeable   = [i for i in instruments if i["asset_class"] in ("Equity","Bond")]
    break_types = ["Quantity","Price","Missing","Corporate Action"]
    statuses    = ["Open","Open","Open","Investigating","Resolved"]
    for _ in range(30):
        inst   = random.choice(tradeable)
        iq     = round(random.uniform(1000, 50000), 0)
        diff   = random.choice([-200,-100,-50,50,100,200,500])
        status = random.choice(statuses)
        supabase.table("reconciliation_breaks").upsert({
            "break_id":        f"BRK-{uid()}",
            "fund_id":         random.choice(fund_ids),
            "isin":            inst["isin"],
            "internal_qty":    iq,
            "custodian_qty":   iq + diff,
            "break_qty":       abs(diff),
            "break_value_eur": round(abs(diff) * inst["price"], 2),
            "break_type":      random.choice(break_types),
            "status":          status,
            "created_date":    str(TODAY - timedelta(days=random.randint(0, 5))),
            "resolved_date":   str(TODAY) if status == "Resolved" else None,
        }).execute()


if __name__ == "__main__":
    print("Fetching prices...")
    instruments = fetch_prices()
    print(f"  {len(instruments)} instruments priced.")
    print("Inserting instruments..."); insert_instruments(instruments)
    print("Inserting funds...");       insert_funds()
    print("Inserting counterparties..."); insert_counterparties()
    print("Inserting SSIs...");        insert_ssis(instruments)
    print("Inserting positions...");   insert_positions(instruments)
    print("Inserting trades...");      insert_trades(instruments)
    print("Inserting breaks...");      insert_breaks(instruments)
    print("Done.")