"""Static definition of the dashboard universe.

Real public data:  fund identifiers and metadata (ISIN, name, domicile, inception),
                   instrument identifiers (ISIN, listing), counterparty names and LEIs
                   (checked against the GLEIF register), prices, FX rates, NAV and dividends
                   (Yahoo Finance, refreshed by update_prices.py).
Simulated:         positions, trades, settlement instructions and reconciliation breaks
                   (these are internal records of a fund administrator and are not published).
"""
from datetime import date

# AUM anchor: fund size in EUR million taken from the issuer data on this date.
# AUM on any other date is scaled with NAV (shares outstanding held constant).
AUM_ANCHOR_DATE = date(2026, 10, 15)

# fund_id = Xetra / Euronext ticker of the line used for NAV.
# (fund_id, name, isin, nav_ticker, domicile, inception, aum_eur_m, region universe)
FUNDS = [
    ("IWDA", "iShares Core MSCI World UCITS ETF USD (Acc)",      "IE00B4L5Y983", "IWDA.AS", "IE", "2009-09-25", 133518, "world"),
    ("VWCE", "Vanguard FTSE All-World UCITS ETF (USD) Acc",      "IE00BK5BQT80", "VWCE.DE", "IE", "2019-07-23",  55448, "world"),
    ("SXR8", "iShares Core S&P 500 UCITS ETF USD (Acc)",         "IE00B5BMR087", "SXR8.DE", "IE", "2010-05-19", 141386, "us"),
    ("EXSA", "iShares STOXX Europe 600 UCITS ETF (DE)",          "DE0002635307", "EXSA.DE", "DE", "2004-02-13",   9452, "europe"),
    ("IMEU", "iShares Core MSCI Europe UCITS ETF EUR (Dist)",    "IE00B1YZSC51", "IMEU.AS", "IE", "2007-07-06",  10567, "europe"),
]

# Number of positions held per fund (a sleeve of its real constituents).
SLEEVE_SIZE = {"IWDA": 16, "VWCE": 18, "SXR8": 11, "EXSA": 11, "IMEU": 12}

# ticker: (isin, name, currency, exchange, country, region)
# Quotes on the London Stock Exchange are in pence (GBp); handled in update_prices.py.
STOCKS = {
    "AAPL":     ("US0378331005", "Apple Inc",                 "USD", "NASDAQ",             "US", "us"),
    "MSFT":     ("US5949181045", "Microsoft Corp",            "USD", "NASDAQ",             "US", "us"),
    "NVDA":     ("US67066G1040", "NVIDIA Corp",               "USD", "NASDAQ",             "US", "us"),
    "AMZN":     ("US0231351067", "Amazon.com Inc",            "USD", "NASDAQ",             "US", "us"),
    "GOOGL":    ("US02079K3059", "Alphabet Inc Class A",      "USD", "NASDAQ",             "US", "us"),
    "META":     ("US30303M1027", "Meta Platforms Inc",        "USD", "NASDAQ",             "US", "us"),
    "JPM":      ("US46625H1005", "JPMorgan Chase & Co",       "USD", "NYSE",               "US", "us"),
    "JNJ":      ("US4781601046", "Johnson & Johnson",         "USD", "NYSE",               "US", "us"),
    "XOM":      ("US30231G1022", "Exxon Mobil Corp",          "USD", "NYSE",               "US", "us"),
    "V":        ("US92826C8394", "Visa Inc",                  "USD", "NYSE",               "US", "us"),
    "LLY":      ("US5324571083", "Eli Lilly and Co",          "USD", "NYSE",               "US", "us"),
    "WMT":      ("US9311421039", "Walmart Inc",               "USD", "NYSE",               "US", "us"),
    "PG":       ("US7427181091", "Procter & Gamble Co",       "USD", "NYSE",               "US", "us"),
    "ASML.AS":  ("NL0010273215", "ASML Holding NV",           "EUR", "Euronext Amsterdam", "NL", "europe"),
    "INGA.AS":  ("NL0011821202", "ING Groep NV",              "EUR", "Euronext Amsterdam", "NL", "europe"),
    "SAP.DE":   ("DE0007164600", "SAP SE",                    "EUR", "Xetra",              "DE", "europe"),
    "SIE.DE":   ("DE0007236101", "Siemens AG",                "EUR", "Xetra",              "DE", "europe"),
    "ALV.DE":   ("DE0008404005", "Allianz SE",                "EUR", "Xetra",              "DE", "europe"),
    "IBE.MC":   ("ES0144580Y14", "Iberdrola SA",              "EUR", "Bolsa de Madrid",    "ES", "europe"),
    "NESN.SW":  ("CH0038863350", "Nestle SA",                 "CHF", "SIX Swiss Exchange", "CH", "europe"),
    "NOVN.SW":  ("CH0012005267", "Novartis AG",               "CHF", "SIX Swiss Exchange", "CH", "europe"),
    "ROG.SW":   ("CH0012032048", "Roche Holding AG",          "CHF", "SIX Swiss Exchange", "CH", "europe"),
    "NOVO-B.CO":("DK0062498333", "Novo Nordisk A/S",          "DKK", "Nasdaq Copenhagen",  "DK", "europe"),
    "AZN.L":    ("GB0009895292", "AstraZeneca PLC",           "GBP", "London Stock Exchange", "GB", "europe"),
    "HSBA.L":   ("GB0005405286", "HSBC Holdings PLC",         "GBP", "London Stock Exchange", "GB", "europe"),
    "SHEL.L":   ("GB00BP6MXD84", "Shell PLC",                 "GBP", "London Stock Exchange", "GB", "europe"),
    "ULVR.L":   ("GB00B10RZP78", "Unilever PLC",              "GBP", "London Stock Exchange", "GB", "europe"),
    "7203.T":   ("JP3633400001", "Toyota Motor Corp",         "JPY", "Tokyo Stock Exchange", "JP", "japan"),
    "6758.T":   ("JP3435000009", "Sony Group Corp",           "JPY", "Tokyo Stock Exchange", "JP", "japan"),
}

# Spot FX used to value positions in EUR: ticker: (id, name, quote currency)
FX = {
    "EURUSD=X": ("EUR/USD", "EUR/USD Spot", "USD"),
    "EURGBP=X": ("EUR/GBP", "EUR/GBP Spot", "GBP"),
    "EURCHF=X": ("EUR/CHF", "EUR/CHF Spot", "CHF"),
    "EURJPY=X": ("EUR/JPY", "EUR/JPY Spot", "JPY"),
    "EURDKK=X": ("EUR/DKK", "EUR/DKK Spot", "DKK"),
}

# Which stocks each fund universe can hold
UNIVERSE_REGIONS = {
    "world":  {"us", "europe", "japan"},
    "us":     {"us"},
    "europe": {"europe"},
}

# Place of settlement (central securities depository BIC) by country of the issuer
CSD_BIC = {
    "US": "DTCYUS33XXX",  # DTC
    "DE": "DAKVDEFFXXX",  # Clearstream Banking Frankfurt
    "NL": "NECINL2AXXX",  # Euroclear Nederland
    "ES": "IBRCESMMXXX",  # Iberclear
    "CH": "INSECHZZXXX",  # SIX SIS
    "DK": "VPSKDK22XXX",  # VP Securities
    "GB": "CRSTGB22XXX",  # Euroclear UK & International
    "JP": "JASDJPJTXXX",  # JASDEC
}

# Standard settlement cycle in business days (US moved to T+1 in May 2024; EU, UK, CH, JP are T+2)
SETTLEMENT_CYCLE = {"US": 1}
DEFAULT_CYCLE = 2

# (id, name, bic, lei, type, country, kyc_status)  LEIs checked against the GLEIF register.
COUNTERPARTIES = [
    ("CP01", "Goldman Sachs International", "GSILGB2XXXX", "W22LROWP2IHZNBB6K528", "Broker",    "GB", "Approved"),
    ("CP02", "J.P. Morgan SE",              "JPMGDEFFXXX", "549300ZK53CNGEEI6A29", "Broker",    "DE", "Approved"),
    ("CP03", "Deutsche Bank AG",            "DEUTDEFFXXX", "7LTWFZYICNSX8D621K86", "Broker",    "DE", "Approved"),
    ("CP04", "Euroclear Bank",              "MGTCBEBEECL", "549300OZ46BRLZ8Y6F65", "Custodian", "BE", "Approved"),
    ("CP05", "Clearstream Banking S.A.",    "CEDELULLXXX", "549300OL514RA0SXJJ44", "Custodian", "LU", "Approved"),
    ("CP06", "Eurex Clearing AG",           "ECAGDEFFXXX", "529900LN3S50JPU47S06", "CCP",       "DE", "Approved"),
    ("CP07", "Barclays Bank PLC",           "BARCGB22XXX", "G5GSEF7VJP5I7OUK5573", "Broker",    "GB", "Approved"),
    ("CP08", "UBS Europe SE",               "UBSWDEFFXXX", "5299007QVIQ7IO64NX37", "Broker",    "DE", "Pending"),
    ("CP09", "ABN AMRO Bank N.V.",          "ABNANL2AXXX", "BFXS5XCH7N0Y05NIXW11", "Broker",    "NL", "Approved"),
    ("CP10", "Raiffeisen Bank International AG", "RZBAATWWXXX", "9ZHRYM6F437SQJ6OUG95", "Broker", "AT", "Expired"),
]

BROKERS_ACTIVE = ["CP01", "CP02", "CP03", "CP07", "CP09"]   # normal execution counterparties
BROKERS_ALL = BROKERS_ACTIVE + ["CP08", "CP10"]              # CP08 pending KYC, CP10 expired KYC
