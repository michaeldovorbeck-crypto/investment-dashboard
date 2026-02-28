import streamlit as st
import yfinance as yf

st.set_page_config(page_title="My Portfolio", layout="wide")

st.title("📈 My Investment Dashboard")

# Din portefølje (rediger frit)
portfolio = [
    "NVDA",
    "TSLA",
    "MSFT",
    "ARKQ",
    "META"
]

selected = st.selectbox("Choose stock", portfolio)

data = yf.download(selected, period="1y")

col1, col2 = st.columns([3, 1])

with col1:
    st.line_chart(data["Close"])

with col2:
    st.metric("Last price", round(data["Close"].iloc[-1], 2))
