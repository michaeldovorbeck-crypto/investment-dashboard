import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import yfinance as yf

from engine import screen_universe
from universe_us import get_sp500_universe

st.set_page_config(page_title="Investment Dashboard", layout="wide")
st.title("📊 Investment Dashboard (EU + US + Tema-radar)")

# ---------- Helpers ----------
def safe_col(row, *cols, default=""):
    for c in cols:
        try:
            if c in row and pd.notna(row[c]):
                return row[c]
        except Exception:
            pass
    return default

def load_csv_universe(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=["ticker", "name"])
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        return pd.DataFrame(columns=["ticker", "name"])
    if "name" not in df.columns and "Navn" in df.columns:
        df = df.rename(columns={"Navn": "name"})
    if "name" not in df.columns:
        df["name"] = ""
    return df[["ticker", "name"]].dropna().drop_duplicates(subset=["ticker"])

@st.cache_data(ttl=3600)
def download_close_cached(ticker: str, period: str) -> pd.DataFrame:
    return yf.download(ticker, period=period, auto_adjust=True, progress=False)

@st.cache_data(ttl=3600)
def theme_radar_cached() -> pd.DataFrame:
    themes = pd.DataFrame(
        [
            ("AI & Software", "QQQ"),
            ("Semiconductors", "SOXX"),
            ("Elektrificering & batterier", "LIT"),
            ("Grøn energi", "ICLN"),
            ("Solenergi", "TAN"),
            ("Defense/Aerospace", "ITA"),
            ("Robotics/Automation", "BOTZ"),
            ("Rumd / Space", "ARKX"),
            ("Cybersecurity", "HACK"),
        ],
        columns=["Tema", "Ticker"],
    )
    base = "SPY"
    tickers = [base] + themes["Ticker"].tolist()
    px = yf.download(tickers, period="1y", auto_adjust=True, progress=False)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame()
    px = px.dropna()
    if base not in px.columns or len(px) < 80:
        return pd.DataFrame()

    def ret(days: int):
        return px.pct_change(days).iloc[-1]

    spy_1m = float(ret(21).get(base, 0))
    spy_3m = float(ret(63).get(base, 0))

    out = []
    for _, r in themes.iterrows():
        t = r["Ticker"]
        if t not in px.columns:
            continue
        rs_1m = float(ret(21).get(t, 0) - spy_1m)
        rs_3m = float(ret(63).get(t, 0) - spy_3m)
        score = 60 * rs_3m + 40 * rs_1m
        out.append([r["Tema"], t, score, rs_1m, rs_3m])

    df = pd.DataFrame(out, columns=["Tema", "Ticker", "MomentumScore", "RS_1M_vs_SPY", "RS_3M_vs_SPY"])
    return df.sort_values("MomentumScore", ascending=False)

def render_help(top_df: pd.DataFrame, label: str, universe_size: int):
    with st.sidebar.expander("🧭 Hjælp: hvad ser jeg?", expanded=True):
        st.markdown("""
**Formål**
- Scanner markeder og viser en **shortlist (Top N)** af tekniske setups.
- **Ikke finansiel rådgivning**.

**Signal**
- **A_Risk**: ✅ OK | ⚠️ risiko | 🚨 høj risiko
- **B_Buy**: 🟢 “buy-early zone”
- **C_Timing**: 🔵 hold/add | 🟡 take-profit watch | 🔴 exit-risk
""")
        st.caption(f"Univers: {universe_size} | Opdateret: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        if top_df is not None and not top_df.empty:
            st.markdown(f"### ⭐ {label} – Top kandidater")
            for i, row in top_df.reset_index(drop=True).head(10).iterrows():
                t = safe_col(row, "Ticker", "ticker")
                n = safe_col(row, "Navn", "name")
                why = safe_col(row, "Hvorfor", "Why")
                sc = safe_col(row, "Score")
                st.markdown(f"**{i+1}. {t}** {('— ' + str(n)) if n else ''}  \nScore **{sc}** — {why}")

# ---------- UI ----------
st.sidebar.header("Indstillinger")
top_n = st.sidebar.slider("Top N", 5, 30, 10)

tabs = st.tabs(["🇪🇺 Europa", "🇺🇸 USA (S&P 500)", "🔎 Vælg aktie & graf", "🧭 Tema/forecast"])

# --- EUROPA ---
with tabs[0]:
    st.subheader("Europa-univers (STOXX600 + ekstra SE/DE/DK)")
    eu1 = load_csv_universe("data/stoxx600.csv")
    eu2 = load_csv_universe("data/extra_se_de_dk.csv")
    eu = pd.concat([eu1, eu2], ignore_index=True).drop_duplicates(subset=["ticker"])
    st.write(f"Antal aktier: **{len(eu)}**")

    with st.spinner("Scanner Europa..."):
        eu_top = screen_universe(eu, top_n=top_n)

    render_help(eu_top, "Europa", universe_size=len(eu))
    st.dataframe(eu_top, use_container_width=True)

    st.subheader("Graf")
    if eu_top is not None and not eu_top.empty:
        options = [f"{r['Ticker']} — {r.get('Navn','')}".strip(" —") for _, r in eu_top.iterrows()]
        pick_label = st.selectbox("Vælg kandidat", options, key="eu_pick")
        pick = pick_label.split("—")[0].strip()
        period = st.selectbox("Periode", ["6mo", "1y", "2y", "5y"], index=1, key="eu_period")
        px = download_close_cached(pick, period)
        if not px.empty:
            st.line_chart(px["Close"])

# --- USA (S&P500) ---
with tabs[1]:
    st.subheader("USA – S&P 500 (alle)")
    st.caption("Hentes kun når du klikker – så appen crasher ikke hvis Wikipedia fejler.")

    if st.button("Hent S&P500 liste", key="btn_sp500"):
        df, msg = get_sp500_universe()
        st.session_state["sp500_df"] = df
        st.session_state["sp500_msg"] = msg

    sp500_df = st.session_state.get("sp500_df", pd.DataFrame(columns=["ticker", "name"]))
    sp500_msg = st.session_state.get("sp500_msg", "Klik 'Hent S&P500 liste' for at starte.")

    st.info(sp500_msg)
    st.write(f"S&P500 i hukommelse: **{len(sp500_df)}**")

    if not sp500_df.empty and st.button("Kør S&P500 scan", key="btn_sp500_scan"):
        with st.spinner("Scanner S&P500..."):
            us_top = screen_universe(sp500_df, top_n=top_n)

        render_help(us_top, "USA", universe_size=len(sp500_df))
        st.dataframe(us_top, use_container_width=True)

        st.subheader("Graf")
        if not us_top.empty:
            pick = st.selectbox("Vælg kandidat", us_top["Ticker"].tolist(), key="us_pick")
            period = st.selectbox("Periode", ["6mo", "1y", "2y", "5y"], index=1, key="us_period")
            px = download_close_cached(pick, period)
            if not px.empty:
                st.line_chart(px["Close"])

# --- MANUEL GRAF ---
with tabs[2]:
    st.subheader("Vælg aktie & graf")
    ticker = st.text_input("Ticker (Yahoo-format)", value="NVDA").strip().upper()
    period = st.selectbox("Periode", ["6mo", "1y", "2y", "5y"], index=1, key="manual_period")
    px = download_close_cached(ticker, period)
    if px.empty:
        st.warning("Ingen data fundet – tjek ticker.")
    else:
        st.line_chart(px["Close"])

# --- TEMA ---
with tabs[3]:
    st.subheader("Tema/forecast radar")
    radar = theme_radar_cached()
    if radar.empty:
        st.warning("Kunne ikke hente tema-data lige nu.")
    else:
        st.dataframe(radar, use_container_width=True)
        st.markdown("### 🔥 Temaer med stærk relativ styrke (teknisk momentum)")
        for _, r in radar.head(6).iterrows():
            st.markdown(
                f"- **{r['Tema']}** ({r['Ticker']}) — RS 1M: {r['RS_1M_vs_SPY']:.2%}, RS 3M: {r['RS_3M_vs_SPY']:.2%}"
            )
