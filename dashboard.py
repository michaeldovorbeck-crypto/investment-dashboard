import streamlit as st
import yfinance as yf

st.title("📈 My Investment Dashboard")

ticker = st.text_input("Enter ticker", "NVDA")

data = yf.download(ticker, period="1y")

st.line_chart(data["Close"])
