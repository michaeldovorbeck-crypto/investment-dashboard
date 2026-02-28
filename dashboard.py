import streamlit as st
import yfinance as yf
from engine import run_engine, DEFAULT_PORTFOLIO

st.set_page_config(page_title="Investment Dashboard", layout="wide")
st.title("📈 My Investment Dashboard (Momentum + Rotation)")

# Portfolio editor
st.sidebar.header("Portfolio")
portfolio_text = st.sidebar.text_area(
    "Tickers (one per line)",
    "\n".join(DEFAULT_PORTFOLIO),
    height=160
)
portfolio = [t.strip().upper() for t in portfolio_text.splitlines() if t.strip()]

# Run engine
with st.spinner("Loading data & computing signals..."):
    signals, themes, meta, close = run_engine(portfolio=portfolio)

# Top metrics
c1, c2, c3 = st.columns(3)
c1.metric("Market Regime", meta.get("MarketRegime", "N/A"))
c2.metric("Portfolio Temperature", str(meta.get("PortfolioTemperature", "N/A")))
tb = meta.get("TrendBreadth")
c3.metric("Trend Breadth", f"{tb:.0%}" if tb is not None else "N/A")

st.subheader("Top Themes (Rotation Radar)")
st.dataframe(themes.head(10), use_container_width=True)

st.subheader("Portfolio Signals (Ranked)")
st.dataframe(signals, use_container_width=True)

st.subheader("Chart")
if len(signals):
    ticker = st.selectbox("Select ticker", signals["Ticker"].tolist())
    period = st.selectbox("Period", ["6mo","1y","2y","5y"], index=1)
    px = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    st.line_chart(px["Close"])
else:
    st.info("No signals computed yet (check tickers / data availability).")
