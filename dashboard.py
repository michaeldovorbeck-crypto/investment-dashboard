import os
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import yfinance as yf

from engine import screen_universe
from universe_stoxx import get_stoxx600_yahoo_tickers

st.set_page_config(page_title="Europe Screener", layout="wide")
st.title("📈 Europe Screener (STOXX 600 + SE/DE/DK)")

# ---------- Helpers ----------
def load_csv_tickers(path):
    if not os.path.exists(path):
        return []
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        return []
    return df["ticker"].dropna().astype(str).tolist()

@st.cache_data(ttl=6*3600)
def load_stoxx600_cached():
    tickers, source_url = get_stoxx600_yahoo_tickers()
    return tickers, source_url

@st.cache_data(ttl=3600)
def screen_cached(tickers_tuple, top_n):
    return screen_universe(list(tickers_tuple), top_n=top_n)

def render_help(top_df, source_url, universe_size):
    with st.sidebar.expander("📌 Help / What am I looking at?", expanded=True):
        st.markdown("""
**What this dashboard does**
- Builds a Europe stock universe and ranks **technical setups** (not financial advice).
- Focus: momentum/trend + timing using RSI and moving averages.

**Signals**
- **A_Risk**: ✅ OK | ⚠️ rising risk | 🚨 high risk (trend break / deep drawdown)
- **B_Buy**: 🟢 “Buy-early zone” (trend OK + RSI in buy-range + RSI improving)
- **C_Timing**: 🔵 hold/add | 🟡 take-profit watch | 🔴 exit risk

**How to use Top 10**
- Treat it as a **shortlist**:
  1) open chart,
  2) check news/earnings,
  3) decide position size & risk.
""")
        st.caption(f"Universe size loaded: {universe_size}")
        st.caption(f"STOXX 600 source (selection list PDF): {source_url}")
        st.caption(f"Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

        st.markdown("### ⭐ Top candidates to look at now")
        for i, row in top_df.iterrows():
            st.markdown(f"**{i+1}. {row['Ticker']}** — Score {row['Score']} — {row['Why']}")

# ---------- Sidebar controls ----------
st.sidebar.header("Universe")
include_stoxx = st.sidebar.checkbox("Include STOXX Europe 600", value=True)
include_extra = st.sidebar.checkbox("Include extra list (SE/DE/DK)", value=True)
top_n = st.sidebar.slider("Top N", 5, 30, 10)

# ---------- Build universe ----------
tickers = []
source_url = "N/A"

if include_stoxx:
    with st.spinner("Loading STOXX 600 universe..."):
        stoxx_tickers, source_url = load_stoxx600_cached()
    tickers += stoxx_tickers

if include_extra:
    tickers += load_csv_tickers("data/extra_se_de_dk.csv")

tickers = sorted(set([t.strip().upper() for t in tickers if t.strip()]))

# ---------- Run screener ----------
if not tickers:
    st.error("No tickers loaded. Check sidebar selections and data/extra_se_de_dk.csv")
    st.stop()

with st.spinner("Screening universe..."):
    top = screen_cached(tuple(tickers), top_n)

if top.empty:
    st.warning("No results (data missing / symbols not available on Yahoo).")
    st.stop()

# ---------- Render help + main views ----------
render_help(top, source_url, universe_size=len(tickers))

st.subheader(f"Top {top_n} candidates (ranked)")
st.dataframe(top, use_container_width=True)

st.subheader("Chart")
ticker = st.selectbox("Select ticker", top["Ticker"].tolist())
period = st.selectbox("Period", ["6mo", "1y", "2y", "5y"], index=1)
px = yf.download(ticker, period=period, auto_adjust=True, progress=False)
st.line_chart(px["Close"])
