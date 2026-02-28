import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import yfinance as yf

from engine import screen_universe
from universe_us import get_sp500_universe

st.set_page_config(page_title="Investment Dashboard", layout="wide")
st.title("📊 Investment Dashboard (EU + US + Tema-radar)")

# -----------------------------
# Helpers
# -----------------------------
def safe_col(row, primary, fallback=None, default=""):
    """Returnér kolonneværdi robust (Series/dict)."""
    try:
        if primary in row and pd.notna(row[primary]):
            return row[primary]
    except Exception:
        pass
    if fallback:
        try:
            if fallback in row and pd.notna(row[fallback]):
                return row[fallback]
        except Exception:
            pass
    return default

def load_csv_universe(path: str) -> pd.DataFrame:
    """
    Læser et univers fra CSV.
    Understøtter:
      - ticker,name
      - ticker,Navn
      - ticker alene
    """
    if not os.path.exists(path):
        return pd.DataFrame(columns=["ticker", "name"])

    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        return pd.DataFrame(columns=["ticker", "name"])

    if "name" not in df.columns and "Navn" in df.columns:
        df = df.rename(columns={"Navn": "name"})

    if "name" not in df.columns:
        df["name"] = ""

    df["ticker"] = df["ticker"].astype(str).str.strip()
    df["name"] = df["name"].astype(str)

    df = df[df["ticker"] != ""].drop_duplicates(subset=["ticker"])
    return df[["ticker", "name"]]

@st.cache_data(ttl=6 * 3600)
def load_sp500_cached() -> pd.DataFrame:
    """Hent S&P 500 (ticker + name) og cache 6 timer."""
    return get_sp500_universe()

@st.cache_data(ttl=3600)
def download_close_cached(ticker: str, period: str) -> pd.DataFrame:
    """Cache chart downloads så vi ikke spammer yfinance."""
    return yf.download(ticker, period=period, auto_adjust=True, progress=False)

@st.cache_data(ttl=3600)
def theme_radar_cached() -> pd.DataFrame:
    """
    Tema/forecast radar via ETF proxies.
    Høj score = relativ styrke vs SPY (1M og 3M vægtet).
    """
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
        st.markdown(f"""
**Formål**
- Dashboardet scanner markeder og viser en **shortlist** (Top N) af tekniske setups.
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
        st.caption(f"Univers-størrelse: {universe_size}")
        st.caption(f"Opdateret: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

        if top_df is not None and not top_df.empty:
            st.markdown(f"### ⭐ {label} – kandidater værd at se nærmere på")
            tmp = top_df.reset_index(drop=True).head(10)
            for i, row in tmp.iterrows():
                ticker = safe_col(row, "Ticker", "ticker", "")
                navn = safe_col(row, "Navn", "name", "")
                hvorfor = safe_col(row, "Hvorfor", "Why", "")
                score = safe_col(row, "Score", None, "")
                st.markdown(
                    f"**{i+1}. {ticker}** {('— ' + str(navn)) if navn else ''}  \n"
                    f"Score **{score}** — {hvorfor}"
                )

# -----------------------------
# Sidebar settings
# -----------------------------
st.sidebar.header("Indstillinger")
top_n = st.sidebar.slider("Top N", 5, 30, 10)

# -----------------------------
# Tabs
# -----------------------------
tabs = st.tabs(["🇪🇺 Europa", "🇺🇸 USA (S&P 500)", "🔎 Vælg aktie & graf", "🧭 Tema/forecast"])

# =============================
# TAB 1: EUROPA
# =============================
with tabs[0]:
    st.subheader("Europa-univers (STOXX600 + ekstra SE/DE/DK)")

    eu1 = load_csv_universe("data/stoxx600.csv")
    eu2 = load_csv_universe("data/extra_se_de_dk.csv")
    eu = pd.concat([eu1, eu2], ignore_index=True).drop_duplicates(subset=["ticker"])

    st.write(f"Antal aktier i EU-univers: **{len(eu)}**")

    with st.spinner("Scanner Europa..."):
        eu_top = screen_universe(eu, top_n=top_n)

    render_help(eu_top, "Europa Top-liste", universe_size=len(eu))

    st.dataframe(eu_top, use_container_width=True)

    st.subheader("Graf")
    if eu_top is not None and not eu_top.empty:
        # Vis "Ticker — Navn" i dropdown
        options = []
        for _, r in eu_top.iterrows():
            t = safe_col(r, "Ticker", "ticker", "")
            n = safe_col(r, "Navn", "name", "")
            label = f"{t} — {n}" if n else t
            options.append((label, t))

        pick_label = st.selectbox("Vælg kandidat", [o[0] for o in options], key="eu_pick")
        pick = dict(options).get(pick_label, options[0][1])

        period = st.selectbox("Periode", ["6mo", "1y", "2y", "5y"], index=1, key="eu_period")
        px = download_close_cached(pick, period)
        if px.empty:
            st.warning("Ingen data fundet for denne ticker.")
        else:
            st.line_chart(px["Close"])
    else:
        st.info("Ingen resultater endnu — tjek tickers i CSV-filerne.")

# =============================
# TAB 2: USA (S&P500)
# =============================
with tabs[1]:
    st.subheader("USA – S&P 500 (alle)")
    st.caption("Listen hentes automatisk (ticker + navn) og caches i 6 timer.")

    sp500 = load_sp500_cached()
    st.write(f"S&P 500 aktier loaded: **{len(sp500)}**")

    st.warning("S&P 500 scan er tungt. Brug knappen, så du ikke kører scan hele tiden.")

    run_scan = st.button("Kør S&P 500 scan (Top N)")
    if run_scan:
        with st.spinner("Scanner S&P 500... (første gang kan tage et par minutter)"):
            us_top = screen_universe(sp500, top_n=top_n)

        render_help(us_top, "USA Top-liste", universe_size=len(sp500))

        st.dataframe(us_top, use_container_width=True)

        st.subheader("Graf")
        if us_top is not None and not us_top.empty:
            options = []
            for _, r in us_top.iterrows():
                t = safe_col(r, "Ticker", "ticker", "")
                n = safe_col(r, "Navn", "name", "")
                label = f"{t} — {n}" if n else t
                options.append((label, t))

            pick_label = st.selectbox("Vælg kandidat", [o[0] for o in options], key="us_pick")
            pick = dict(options).get(pick_label, options[0][1])

            period = st.selectbox("Periode", ["6mo", "1y", "2y", "5y"], index=1, key="us_period")
            px = download_close_cached(pick, period)
            if px.empty:
                st.warning("Ingen data fundet for denne ticker.")
            else:
                st.line_chart(px["Close"])

# =============================
# TAB 3: MANUEL GRAF
# =============================
with tabs[2]:
    st.subheader("Vælg hvilken som helst aktie og se graf")
    st.caption("Skriv ticker (Yahoo-format) fx: NOVO-B.CO, SAP.DE, NVDA, MSFT, ASML.AS")

    manual = st.text_input("Ticker", value="NVDA").strip().upper()
    period = st.selectbox("Periode", ["6mo", "1y", "2y", "5y"], index=1, key="manual_period")

    if manual:
        px = download_close_cached(manual, period)
        if px.empty:
            st.error("Ingen data fundet. Tjek ticker-formatet (Yahoo).")
        else:
            st.line_chart(px["Close"])

# =============================
# TAB 4: TEMA/FORECAST
# =============================
with tabs[3]:
    st.subheader("Tema/forecast radar (hvor roterer momentum hen?)")
    st.caption("Teknisk radar baseret på tema-ETF’er som proxy. Høj score = relativ styrke vs SPY.")

    radar = theme_radar_cached()
    if radar.empty:
        st.warning("Kunne ikke hente data til tema-radar lige nu.")
    else:
        st.dataframe(radar, use_container_width=True)

        st.markdown("### 🔥 Mulige områder at undersøge nærmere (teknisk momentum)")
        for _, r in radar.head(6).iterrows():
            st.markdown(
                f"- **{r['Tema']}** ({r['Ticker']}) — RS 1M: {r['RS_1M_vs_SPY']:.2%}, RS 3M: {r['RS_3M_vs_SPY']:.2%}"
            )
