import os
import time
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import streamlit as st
import yfinance as yf


# ----------------------------
# App config
# ----------------------------
st.set_page_config(page_title="Nordnet-style Dashboard", layout="wide")
st.title("📊 Nordnet-style Investment Dashboard")


# ----------------------------
# Utilities
# ----------------------------
PORTFOLIO_FILE = "data/portfolio_alloc.csv"

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def load_portfolio_alloc() -> pd.DataFrame:
    if not os.path.exists(PORTFOLIO_FILE):
        return pd.DataFrame(columns=["name", "ticker", "weight_pct"])

    df = pd.read_csv(PORTFOLIO_FILE)
    # Normalize columns
    expected = {"name", "ticker", "weight_pct"}
    for col in expected:
        if col not in df.columns:
            df[col] = ""

    df["name"] = df["name"].astype(str).fillna("")
    df["ticker"] = df["ticker"].astype(str).fillna("").str.strip().str.upper()
    df["weight_pct"] = pd.to_numeric(df["weight_pct"], errors="coerce").fillna(0.0)

    # Keep order as in file
    return df[["name", "ticker", "weight_pct"]]

@st.cache_data(ttl=60*30)
def batch_daily_prices(tickers: list[str]) -> pd.DataFrame:
    """
    Henter dagskurser for mange tickers i ét kald (hurtigere/mer stabilt).
    Return: DataFrame med kolonner: ticker, last, prev_close, chg, chg_pct
    """
    tickers = [t for t in tickers if t and t != "CASH"]
    if not tickers:
        return pd.DataFrame(columns=["ticker", "last", "prev_close", "chg", "chg_pct"])

    # 5 dage for at sikre vi har "i går"
    data = yf.download(tickers, period="5d", interval="1d", auto_adjust=True, progress=False)

    # yfinance returnerer ofte multiindex kolonner når flere tickers
    # Vi prøver at få "Close" ud robust:
    closes = None
    if isinstance(data.columns, pd.MultiIndex):
        if ("Close" in data.columns.get_level_values(0)):
            closes = data["Close"].copy()
    else:
        # single ticker
        closes = data[["Close"]].rename(columns={"Close": tickers[0]})

    if closes is None or closes.empty:
        return pd.DataFrame(columns=["ticker", "last", "prev_close", "chg", "chg_pct"])

    closes = closes.dropna(how="all")
    if len(closes) < 2:
        return pd.DataFrame(columns=["ticker", "last", "prev_close", "chg", "chg_pct"])

    last_row = closes.iloc[-1]
    prev_row = closes.iloc[-2]

    out = []
    for t in closes.columns:
        try:
            last = float(last_row[t])
            prev = float(prev_row[t])
            chg = last - prev
            chg_pct = (chg / prev) if prev != 0 else 0.0
            out.append([t, last, prev, chg, chg_pct])
        except Exception:
            continue

    return pd.DataFrame(out, columns=["ticker", "last", "prev_close", "chg", "chg_pct"])

@st.cache_data(ttl=60*60*24*7)
def get_sector_cached(ticker: str) -> str:
    """
    Sektor er langsom at hente, så vi cacher 7 dage.
    For ETF'er kan sector være tom; vi forsøger et par felter.
    """
    if not ticker or ticker == "CASH":
        return "Kontanter"

    try:
        info = yf.Ticker(ticker).info or {}
        # Aktier:
        sector = info.get("sector") or info.get("industry")
        # ETF/fund:
        if not sector:
            sector = info.get("category") or info.get("fundFamily") or info.get("quoteType")
        return str(sector) if sector else "Ukendt"
    except Exception:
        return "Ukendt"

@st.cache_data(ttl=60*30)
def yahoo_search(query: str) -> pd.DataFrame:
    """
    Søger efter aktier/ETF'er på Yahoo (navn eller ticker).
    """
    if not query or len(query) < 2:
        return pd.DataFrame(columns=["symbol", "name", "exch", "type"])

    url = "https://query2.finance.yahoo.com/v1/finance/search"
    params = {"q": query, "quotesCount": 12, "newsCount": 0}
    r = requests.get(url, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    js = r.json()

    rows = []
    for q in js.get("quotes", []):
        rows.append([
            q.get("symbol", ""),
            q.get("shortname", "") or q.get("longname", ""),
            q.get("exchDisp", "") or q.get("exchange", ""),
            q.get("quoteType", "")
        ])
    return pd.DataFrame(rows, columns=["symbol", "name", "exch", "type"])

@st.cache_data(ttl=60*15)
def yahoo_news_rss(ticker: str, limit: int = 8) -> list[dict]:
    """
    Henter seneste nyheder via Yahoo RSS.
    """
    if not ticker or ticker == "CASH":
        return []

    rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    try:
        r = requests.get(rss_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
        items = root.findall(".//item")
        out = []
        for it in items[:limit]:
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            out.append({"title": title, "link": link, "pubDate": pub})
        return out
    except Exception:
        return []

def format_pct(x: float) -> str:
    try:
        return f"{x*100:.2f}%"
    except Exception:
        return ""

def format_dkk(x) -> str:
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return ""

def sign_emoji(x: float) -> str:
    if x > 0:
        return "🟢"
    if x < 0:
        return "🔴"
    return "⚪"

def build_portfolio_table(df_port: pd.DataFrame) -> pd.DataFrame:
    """
    Samler portfolio (name,ticker,weight) med dagskurser og sektor.
    """
    tickers = df_port["ticker"].tolist()
    px = batch_daily_prices(tickers)

    merged = df_port.merge(px, how="left", on="ticker")
    merged["sector"] = merged["ticker"].apply(get_sector_cached)

    merged["chg_pct"] = merged["chg_pct"].fillna(0.0)
    merged["chg"] = merged["chg"].fillna(0.0)
    merged["last"] = merged["last"].fillna(float("nan"))

    # Kolonner som “Nordnet-ish”
    merged["I dag"] = merged["chg_pct"].apply(lambda v: f"{sign_emoji(v)} {v*100:+.2f}%")
    merged["Kurs"] = merged["last"].apply(lambda v: "-" if pd.isna(v) else f"{v:.2f}")
    merged["Ticker"] = merged["ticker"]
    merged["Navn"] = merged["name"]
    merged["Vægt"] = merged["weight_pct"].apply(lambda v: f"{v:.2f}%")
    merged["Sektor"] = merged["sector"]

    # Sorter efter vægt
    merged = merged.sort_values("weight_pct", ascending=False)

    return merged


# ----------------------------
# Sidebar
# ----------------------------
st.sidebar.header("Indstillinger")
top_news = st.sidebar.slider("Antal nyheder pr instrument", 3, 15, 6)
chart_period = st.sidebar.selectbox("Standard periode (graf)", ["6mo", "1y", "2y", "5y"], index=1)
st.sidebar.caption(f"Opdateret: {now_utc()}")


# ----------------------------
# Tabs
# ----------------------------
tabs = st.tabs(["🏦 Portefølje", "🔎 Søg & analyse", "🧭 Tema/forecast"])


# ----------------------------
# TAB 1: Portfolio (Nordnet style)
# ----------------------------
with tabs[0]:
    st.subheader("🏦 Min portefølje (Nordnet-style)")
    df_port = load_portfolio_alloc()

    if df_port.empty:
        st.error("Mangler data/portfolio_alloc.csv. Opret filen som beskrevet og commit den.")
        st.stop()

    # Byg tabel med kurser + sektor
    table = build_portfolio_table(df_port)

    # Top KPI’er (baseret på % vægte – ikke kr, da vi ikke har antal/portfolio value)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Antal værdipapirer", f"{len(table)}")
    with col2:
        missing = int((table["ticker"] == "").sum())
        st.metric("Mangler ticker", f"{missing}")
    with col3:
        st.metric("Dagskurser cache", "30 min")

    st.markdown("### Beholdning")
    # “Nordnet-ish” liste med progress bar
    for _, r in table.iterrows():
        name = r["Navn"]
        ticker = r["Ticker"]
        weight = float(r["weight_pct"])
        kurs = r["Kurs"]
        idag = r["I dag"]

        left, right = st.columns([6, 2])
        with left:
            st.markdown(f"**{name}**  \n`{ticker}`  \n{r['Sektor']}")
            st.progress(min(max(weight / 100.0, 0.0), 1.0))
        with right:
            st.markdown(f"**{weight:.2f}%**")
            st.markdown(f"Kurs: **{kurs}**")
            st.markdown(f"{idag}")
        st.divider()

    st.markdown("### Sektorfordeling (baseret på dine % vægte)")
    sector_alloc = (
        table.groupby("Sektor")["weight_pct"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={"weight_pct": "Vægt %"})
    )
    st.dataframe(sector_alloc, use_container_width=True)

    st.markdown("### Klik → detaljer (graf + nyheder)")
    # Dropdown med navn + ticker
    options = []
    for _, r in table.iterrows():
        if r["Ticker"]:
            options.append(f"{r['Navn']} — {r['Ticker']}")
    pick = st.selectbox("Vælg instrument", options, index=0 if options else None)

    if pick:
        ticker = pick.split("—")[-1].strip()
        st.markdown(f"## {ticker}")

        # Kursgraf
        px = yf.download(ticker, period=chart_period, auto_adjust=True, progress=False)
        if not px.empty and "Close" in px.columns:
            st.line_chart(px["Close"])
        else:
            st.warning("Ingen prisdata fundet for denne ticker.")

        # Nyheder
        news = yahoo_news_rss(ticker, limit=top_news)
        st.markdown("### Seneste nyheder")
        if not news:
            st.info("Ingen nyheder fundet (eller Yahoo RSS blokeret for denne ticker).")
        else:
            for n in news:
                # Streamlit linker fint med markdown
                st.markdown(f"- [{n['title']}]({n['link']})  \n  _{n['pubDate']}_")


# ----------------------------
# TAB 2: Search & Analyze (stocks + ETFs)
# ----------------------------
with tabs[1]:
    st.subheader("🔎 Søg efter aktier/ETF’er (navn eller ticker)")
    q = st.text_input("Søg (fx 'Novo', 'ASML', 'AI ETF', 'iShares')", value="")

    if q.strip():
        try:
            res = yahoo_search(q.strip())
            if res.empty:
                st.info("Ingen resultater.")
            else:
                st.dataframe(res, use_container_width=True)

                # Vælg symbol til graf/nyheder
                sym = st.selectbox("Vælg symbol", res["symbol"].tolist())
                st.markdown(f"## {sym}")

                px = yf.download(sym, period=chart_period, auto_adjust=True, progress=False)
                if not px.empty and "Close" in px.columns:
                    st.line_chart(px["Close"])
                else:
                    st.warning("Ingen prisdata fundet.")

                st.markdown("### Seneste nyheder")
                news = yahoo_news_rss(sym, limit=top_news)
                if not news:
                    st.info("Ingen nyheder fundet.")
                else:
                    for n in news:
                        st.markdown(f"- [{n['title']}]({n['link']})  \n  _{n['pubDate']}_")
        except Exception as e:
            st.error(f"Søg fejlede: {e}")

    st.markdown("---")
    st.subheader("📌 Hurtig ticker-check")
    manual = st.text_input("Indtast ticker direkte (Yahoo-format)", value="NVDA").strip().upper()
    if manual:
        px = yf.download(manual, period=chart_period, auto_adjust=True, progress=False)
        if not px.empty and "Close" in px.columns:
            st.line_chart(px["Close"])
        else:
            st.warning("Ingen data – tjek tickerformat.")


# ----------------------------
# TAB 3: Theme / Forecast radar
# ----------------------------
with tabs[2]:
    st.subheader("🧭 Tema/forecast (momentum-proxy via ETF’er)")
    st.caption("Dette er teknisk momentum-indikator (ikke rådgivning).")

    themes = [
        ("AI & Software", "QQQ"),
        ("Semiconductors", "SOXX"),
        ("Elektrificering & batterier", "LIT"),
        ("Grøn energi", "ICLN"),
        ("Solenergi", "TAN"),
        ("Defense/Aerospace", "ITA"),
        ("Robotics/Automation", "BOTZ"),
        ("Rumd / Space", "ARKX"),
        ("Cybersecurity", "HACK"),
    ]

    base = "SPY"
    tickers = [base] + [t for _, t in themes]

    px = yf.download(tickers, period="1y", auto_adjust=True, progress=False)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame()
    px = px.dropna()

    if base not in px.columns or len(px) < 80:
        st.warning("Kunne ikke hente data til tema-radar lige nu.")
    else:
        def ret(days: int):
            return px.pct_change(days).iloc[-1]

        spy_1m = float(ret(21).get(base, 0))
        spy_3m = float(ret(63).get(base, 0))

        rows = []
        for name, t in themes:
            if t not in px.columns:
                continue
            rs_1m = float(ret(21).get(t, 0) - spy_1m)
            rs_3m = float(ret(63).get(t, 0) - spy_3m)
            score = 60 * rs_3m + 40 * rs_1m
            rows.append([name, t, score, rs_1m, rs_3m])

        df = pd.DataFrame(rows, columns=["Tema", "Ticker", "MomentumScore", "RS_1M_vs_SPY", "RS_3M_vs_SPY"])
        df = df.sort_values("MomentumScore", ascending=False)
        st.dataframe(df, use_container_width=True)

        st.markdown("### 🔥 Temaer at kigge nærmere på (stærk relativ styrke)")
        for _, r in df.head(6).iterrows():
            st.markdown(f"- **{r['Tema']}** ({r['Ticker']}) — RS 1M: {r['RS_1M_vs_SPY']:+.2%}, RS 3M: {r['RS_3M_vs_SPY']:+.2%}")
