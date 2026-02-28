import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import yfinance as yf

from engine import screen_universe
from universe_us import get_sp500_universe

st.set_page_config(page_title="Investment Dashboard", layout="wide")
st.title("📊 Investment Dashboard (EU + US + Tema-radar)")

# ---------- Hjælpetekst (altid opdateret + dynamisk top10) ----------
def help_box(top_df: pd.DataFrame, label: str):
    with st.sidebar.expander("🧭 Hjælp: hvad ser jeg?", expanded=True):
        st.markdown(f"""
**Formål**
- Dashboardet scanner markeder og viser en **shortlist** (Top 10/Top N) af tekniske setups.
- Det er **ikke finansiel rådgivning** — brug det som input til din egen beslutning.

**Kolonner**
- **Score (0–100)**: samlet styrke (trend + momentum + stabilitet)
- **A_Risk**: ✅ OK | ⚠️ stigende risiko | 🚨 høj risiko (trend-brud / stort drawdown)
- **B_Buy**: 🟢 Buy-early zone (trend OK + RSI i buy-range og stigende) | ❌ ellers
- **C_Timing**: 🔵 hold/add | 🟡 take-profit watch | 🔴 exit-risk
- **RSI**: momentum (over 70 = ofte “varm”, under ~50 = ofte “kold/tilbagefald”)

**Sådan bruger du Top-listen**
1) Kig på **B_Buy = 🟢** først (entry-zoner).
2) Undgå/skriv dig bag øret hvis **A_Risk = 🚨**.
3) Brug grafen til at bekræfte trend og støtte/modstand.
""")
        st.caption(f"Opdateret: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        if top_df is not None and not top_df.empty:
            st.markdown(f"### ⭐ {label} – kandidater værd at se nærmere på")
            for i, r in top_df.reset_index(drop=True).head(10).iterrows():
                navn = r.get("Navn", "")
                st.markdown(f"**{i+1}. {r['Ticker']}** {('— ' + navn) if navn else ''}  \nScore **{r['Score']}** — {r.get('Hvorfor','')}")

# ---------- Universe loaders ----------
def load_csv_universe(path):
    if not os.path.exists(path):
        return pd.DataFrame(columns=["ticker", "name"])
    df = pd.read_csv(path)
    # accept both "name" or "Navn"
    if "ticker" not in df.columns:
        return pd.DataFrame(columns=["ticker", "name"])
    if "name" not in df.columns and "Navn" in df.columns:
        df = df.rename(columns={"Navn": "name"})
    if "name" not in df.columns:
        df["name"] = ""
    return df[["ticker", "name"]]

@st.cache_data(ttl=6*3600)
def load_sp500_cached():
    return get_sp500_universe()

# ---------- Tema/forecast radar ----------
THEME_ETFS = pd.DataFrame([
    # Tema, ETF proxy
    ("AI & Software", "QQQ"),
    ("Semiconductors", "SOXX"),
    ("Elektrificering & batterier", "LIT"),
    ("Grøn energi", "ICLN"),
    ("Solenergi", "TAN"),
    ("Defense/Aerospace", "ITA"),
    ("Robotics/Automation", "BOTZ"),
    ("Space", "ARKX"),
    ("Cybersecurity", "HACK"),
], columns=["Tema", "Ticker"])

def theme_radar():
    base = "SPY"
    tickers = [base] + THEME_ETFS["Ticker"].tolist()
    px = yf.download(tickers, period="1y", auto_adjust=True, progress=False)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame()
    px = px.dropna()

    if base not in px.columns or len(px) < 60:
        return pd.DataFrame()

    def ret(days):
        return px.pct_change(days).iloc[-1]

    out = []
    spy_1m = ret(21).get(base, 0)
    spy_3m = ret(63).get(base, 0)

    for _, r in THEME_ETFS.iterrows():
        t = r["Ticker"]
        if t not in px.columns:
            continue
        rs_1m = float(ret(21).get(t, 0) - spy_1m)
        rs_3m = float(ret(63).get(t, 0) - spy_3m)

        # simpel “forecast”: temaer med stigende relativ styrke
        score = 60*rs_3m + 40*rs_1m
        out.append([r["Tema"], t, score, rs_1m, rs_3m])

    df = pd.DataFrame(out, columns=["Tema","Ticker","MomentumScore","RS_1M_vs_SPY","RS_3M_vs_SPY"])
    return df.sort_values("MomentumScore", ascending=False)

# ---------- UI ----------
st.sidebar.header("Indstillinger")
top_n = st.sidebar.slider("Top N", 5, 30, 10)

tabs = st.tabs(["🇪🇺 Europa screener", "🇺🇸 USA (S&P 500) screener", "🔎 Vælg aktie & graf", "🧭 Tema/forecast"])

# ----- Europa -----
with tabs[0]:
    st.subheader("Europa-univers (STOXX600 + ekstra SE/DE/DK)")
    eu1 = load_csv_universe("data/stoxx600.csv")
    eu2 = load_csv_universe("data/extra_se_de_dk.csv")
    eu = pd.concat([eu1, eu2], ignore_index=True).drop_duplicates(subset=["ticker"])
    st.write(f"Antal aktier i EU-univers: **{len(eu)}** (du kan udvide stoxx600.csv over tid)")

    with st.spinner("Scanner Europa..."):
        eu_top = screen_universe(eu, top_n=top_n)

    help_box(eu_top, "Europa Top-liste")

    st.dataframe(eu_top, use_container_width=True)

    st.subheader("Graf")
    if not eu_top.empty:
        pick = st.selectbox("Vælg kandidat", eu_top["Ticker"].tolist(), key="eu_pick")
        px = yf.download(pick, period="1y", auto_adjust=True, progress=False)
        st.line_chart(px["Close"])
    else:
        st.info("Ingen resultater endnu — tjek tickers i CSV-filerne.")

# ----- USA S&P 500 -----
with tabs[1]:
    st.subheader("USA – S&P 500 (alle)")
    st.caption("Listen hentes automatisk og caches i 6 timer.")
    sp500 = load_sp500_cached()
    st.write(f"S&P 500 aktier loaded: **{len(sp500)}**")

    # For at undgå at den kører konstant: knap til at starte scan
    run_scan = st.button("Kør S&P 500 scan (kan tage lidt tid)")
    if run_scan:
        with st.spinner("Scanner S&P 500... (første gang kan tage et par minutter)"):
            us_top = screen_universe(sp500, top_n=top_n)

        help_box(us_top, "USA Top-liste")

        st.dataframe(us_top, use_container_width=True)

        st.subheader("Graf")
        if not us_top.empty:
            pick = st.selectbox("Vælg kandidat", us_top["Ticker"].tolist(), key="us_pick")
            px = yf.download(pick, period="1y", auto_adjust=True, progress=False)
            st.line_chart(px["Close"])

    st.warning("Tip: S&P500-scan er tungt. Brug knappen, så du ikke triggere den hele tiden.")

# ----- Vælg aktie & graf (ekstra vindue) -----
with tabs[2]:
    st.subheader("Vælg hvilken som helst aktie og se graf")
    st.caption("Skriv ticker (fx NOVO-B.CO, SAP.DE, NVDA, MSFT, ASML.AS)")

    manual = st.text_input("Ticker", value="NVDA")
    period = st.selectbox("Periode", ["6mo", "1y", "2y", "5y"], index=1)

    px = yf.download(manual.strip().upper(), period=period, auto_adjust=True, progress=False)
    if px.empty:
        st.error("Ingen data fundet. Tjek ticker-formatet (Yahoo).")
    else:
        st.line_chart(px["Close"])

# ----- Tema/Forecast -----
with tabs[3]:
    st.subheader("Tema/forecast radar (hvor roterer momentum hen?)")
    st.caption("Dette er en teknisk ‘radar’ baseret på tema-ETF’er som proxy. Høj score = relativ styrke vs SPY.")

    radar = theme_radar()
    if radar.empty:
        st.warning("Kunne ikke hente data til tema-radar lige nu.")
    else:
        st.dataframe(radar, use_container_width=True)

        top_themes = radar.head(5)
        st.markdown("### 🔥 Mulige områder at undersøge nærmere (teknisk momentum)")
        for _, r in top_themes.iterrows():
            st.markdown(f"- **{r['Tema']}** ({r['Ticker']}) — RS 1M: {r['RS_1M_vs_SPY']:.2%}, RS 3M: {r['RS_3M_vs_SPY']:.2%}")
