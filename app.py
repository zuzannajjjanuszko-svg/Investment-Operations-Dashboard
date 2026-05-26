import os
import pandas as pd
import streamlit as st
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY"))
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(
    page_title="Fund Operations Dashboard",
    page_icon=":bar_chart:",
    layout="wide",
)


@st.cache_data(ttl=300)
def load(table):
    return pd.DataFrame(supabase.table(table).select("*").execute().data)


funds  = load("funds")
inst   = load("instruments")
cps    = load("counterparties")
ssi    = load("settlement_instructions")
pos    = load("positions")
trades = load("trades")
breaks = load("reconciliation_breaks")

st.title("Fund Operations Dashboard")
st.caption("Static data  |  Reconciliation  |  Trade monitoring  |  Fund overview")

tab1, tab2, tab3, tab4 = st.tabs([
    "Static Data", "Reconciliation Breaks", "Trade Monitor", "Fund Overview"
])


# ── TAB 1 — STATIC DATA ──────────────────────────────────────────────
with tab1:

    st.subheader("Instruments")
    ac_filter = st.multiselect(
        "Asset class", inst["asset_class"].unique(),
        default=list(inst["asset_class"].unique())
    )
    st.dataframe(
        inst[inst["asset_class"].isin(ac_filter)]
            [["isin","name","asset_class","currency","exchange","price","price_date","active"]],
        use_container_width=True,
    )

    st.divider()

    st.subheader("Counterparties")
    cp_filter = st.multiselect(
        "Type", cps["cp_type"].unique(), default=list(cps["cp_type"].unique())
    )
    def kyc_colour(row):
        if row["kyc_status"] == "Expired": return ["background-color:#C8A0A0"] * len(row)
        if row["kyc_status"] == "Pending": return ["background-color:#C8B888"] * len(row)
        return [""] * len(row)
    st.dataframe(
        cps[cps["cp_type"].isin(cp_filter)]
           [["counterparty_id","name","bic","lei","cp_type","country","kyc_status","kyc_expiry"]]
           .style.apply(kyc_colour, axis=1),
        use_container_width=True,
    )

    st.divider()

    st.subheader("Settlement Instructions (SSI)")
    c1, c2 = st.columns(2)
    cp_sel     = c1.selectbox("Counterparty", ["All"] + list(cps["name"].sort_values()))
    ssi_status = c2.multiselect(
        "Status", ["Active","Expired","Pending"],
        default=["Active","Expired","Pending"]
    )
    d = (ssi
         .merge(cps[["counterparty_id","name"]], on="counterparty_id", how="left")
         .merge(inst[["isin","name"]], on="isin", how="left", suffixes=("_cp","_inst")))
    d = d[d["status"].isin(ssi_status)]
    if cp_sel != "All":
        d = d[d["name_cp"] == cp_sel]
    def ssi_colour(row):
        if row["status"] == "Expired": return ["background-color:#C8A0A0"] * len(row)
        if row["status"] == "Pending": return ["background-color:#C8B888"] * len(row)
        return [""] * len(row)
    st.dataframe(
        d[["ssi_id","name_cp","name_inst","instruction_type",
           "custodian_bic","currency","valid_from","valid_to","status"]]
         .style.apply(ssi_colour, axis=1),
        use_container_width=True,
    )
    exp = (ssi["status"] == "Expired").sum()
    pnd = (ssi["status"] == "Pending").sum()
    if exp or pnd:
        st.warning(f"{exp} expired SSI(s) and {pnd} pending SSI(s) require attention.")


# ── TAB 2 — RECONCILIATION BREAKS ────────────────────────────────────
with tab2:

    d = (breaks
         .merge(funds[["fund_id","name"]], on="fund_id", how="left")
         .merge(inst[["isin","name","asset_class"]], on="isin", how="left",
                suffixes=("_fund","_inst")))

    open_b    = breaks[breaks["status"] == "Open"]
    inv_b     = breaks[breaks["status"] == "Investigating"]
    today_s   = str(pd.Timestamp.today().date())
    res_today = len(breaks[(breaks["status"]=="Resolved")&(breaks["resolved_date"]==today_s)])

    k1,k2,k3,k4 = st.columns(4)
    k1.metric("Open Breaks",       len(open_b))
    k2.metric("Investigating",      len(inv_b))
    k3.metric("Total Exposure EUR", f"{open_b['break_value_eur'].sum():,.0f}")
    k4.metric("Resolved Today",     res_today)

    st.divider()
    c1,c2,c3 = st.columns(3)
    fund_sel  = c1.selectbox("Fund", ["All"] + list(funds["name"].sort_values()))
    btype_sel = c2.multiselect(
        "Break type", breaks["break_type"].unique().tolist(),
        default=breaks["break_type"].unique().tolist()
    )
    stat_sel  = c3.multiselect(
        "Status", ["Open","Investigating","Resolved"],
        default=["Open","Investigating"]
    )
    if fund_sel != "All":
        d = d[d["name_fund"] == fund_sel]
    d = d[d["break_type"].isin(btype_sel) & d["status"].isin(stat_sel)]

    def brk_colour(row):
        if row["status"] == "Open":          return ["background-color:#C8A0A0"] * len(row)
        if row["status"] == "Investigating": return ["background-color:#C8B888"] * len(row)
        return ["background-color:#A0B8A0"] * len(row)
    st.dataframe(
        d[["break_id","name_fund","isin","name_inst","asset_class",
           "internal_qty","custodian_qty","break_qty","break_value_eur",
           "break_type","status","created_date"]]
         .sort_values("break_value_eur", ascending=False)
         .style.apply(brk_colour, axis=1),
        use_container_width=True,
    )


# ── TAB 3 — TRADE MONITOR ────────────────────────────────────────────
with tab3:

    d = (trades
         .merge(funds[["fund_id","name"]], on="fund_id", how="left")
         .merge(inst[["isin","name","asset_class"]], on="isin", how="left",
                suffixes=("_fund","_inst"))
         .merge(cps[["counterparty_id","name","bic"]], on="counterparty_id",
                how="left", suffixes=("","_cp")))

    d["settlement_date"] = pd.to_datetime(d["settlement_date"]).dt.date
    today = pd.Timestamp.today().date()
    d["overdue"] = (d["settlement_date"] < today) & (d["status"].isin(["Pending","Failed"]))

    active_keys = set(zip(
        ssi[ssi["status"]=="Active"]["counterparty_id"],
        ssi[ssi["status"]=="Active"]["isin"]
    ))
    d["ssi_missing"] = d.apply(
        lambda r: (r["counterparty_id"], r["isin"]) not in active_keys, axis=1
    )

    k1,k2,k3,k4 = st.columns(4)
    k1.metric("Pending", len(d[d["status"]=="Pending"]))
    k2.metric("Settled", len(d[d["status"]=="Settled"]))
    k3.metric("Failed",  len(d[d["status"]=="Failed"]))
    k4.metric("Overdue", int(d["overdue"].sum()))

    st.divider()
    c1,c2 = st.columns(2)
    stat_f   = c1.multiselect(
        "Status", ["Pending","Settled","Failed","Cancelled"],
        default=["Pending","Failed"]
    )
    ssi_only = c2.checkbox("Show only trades with missing Active SSI")
    d = d[d["status"].isin(stat_f)]
    if ssi_only:
        d = d[d["ssi_missing"] == True]

    def trade_colour(row):
        if row["status"]=="Failed" or row["overdue"]: return ["background-color:#C8A0A0"]*len(row)
        if row["ssi_missing"]:                        return ["background-color:#C8B888"]*len(row)
        return [""]*len(row)
    st.dataframe(
        d[["trade_id","name_fund","name_inst","asset_class","trade_type",
           "quantity","price","trade_date","settlement_date","status",
           "name","bic","ssi_missing","overdue"]]
         .rename(columns={"name":"counterparty","bic":"cp_bic"})
         .sort_values("settlement_date")
         .style.apply(trade_colour, axis=1),
        use_container_width=True,
    )


# ── TAB 4 — FUND OVERVIEW ────────────────────────────────────────────
with tab4:

    for _, f in funds.iterrows():
        with st.expander(
            f"{f['name']}  ({f['fund_type']})  —  {f['base_currency']}",
            expanded=False
        ):
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("AUM (EUR)",   f"{f['aum_eur']/1e6:.1f}M")
            c2.metric("NAV / Share", f"{f['nav_per_share']:.4f}")
            c3.metric("Fund Type",   f["fund_type"])
            c4.metric("Domicile",    f["domicile"])

            fp = pos[pos["fund_id"]==f["fund_id"]].merge(
                inst[["isin","asset_class"]], on="isin", how="left"
            )
            if not fp.empty:
                ac = fp.groupby("asset_class")["market_value_eur"].sum().reset_index()
                ac.columns = ["Asset Class","Market Value EUR"]
                ch, tbl = st.columns([1,1])
                ch.bar_chart(ac.set_index("Asset Class"))
                tbl.dataframe(ac, use_container_width=True)