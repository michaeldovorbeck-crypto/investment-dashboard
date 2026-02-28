import numpy as np
import pandas as pd
import yfinance as yf

RSI_BUY_LOW = 35
RSI_BUY_HIGH = 50
RSI_TAKE_PROFIT = 70

def download_close(tickers, period="2y"):
    px = yf.download(tickers, period=period, auto_adjust=True, progress=False)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame()
    return px.dropna(how="all")

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_signals(close_series: pd.Series):
    close = close_series.dropna()
    if len(close) < 220:
        return None

    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    r = rsi(close)

    trend_up = ma50.iloc[-1] > ma200.iloc[-1]
    rsi_now = float(r.iloc[-1])
    rsi_prev = float(r.iloc[-6]) if len(r) > 6 else np.nan

    vol = float(close.pct_change().rolling(20).std().iloc[-1] * 100)
    dd = float((close.iloc[-1] / close.rolling(63).max().iloc[-1]) - 1)

    if (not trend_up) or (dd < -0.15):
        A = "🚨"
    elif vol > 5:
        A = "⚠️"
    else:
        A = "✅"

    buy_early = trend_up and (RSI_BUY_LOW < rsi_now < RSI_BUY_HIGH) and (np.isfinite(rsi_prev) and rsi_now > rsi_prev)
    B = "🟢" if buy_early else "❌"

    if rsi_now > RSI_TAKE_PROFIT:
        C = "🟡 TAKE_PROFIT"
    elif not trend_up:
        C = "🔴 EXIT_RISK"
    else:
        C = "🔵 HOLD/ADD"

    trend_score = 50 if trend_up else 15
    mom_score = max(0, 30 - abs(rsi_now - 55))
    stab_score = max(0, 20 - vol)
    score = float(trend_score + mom_score + stab_score)

    return {
        "Score": round(score, 1),
        "RSI": round(rsi_now, 1),
        "Vol20": round(vol, 2),
        "Drawdown3M": round(dd, 3),
        "TrendUp": bool(trend_up),
        "A_Risk": A,
        "B_Buy": B,
        "C_Timing": C,
        "Last": round(float(close.iloc[-1]), 2),
    }

def screen_universe(df_universe: pd.DataFrame, top_n=10):
    """
    df_universe skal have kolonner: ticker, name (name kan være tom)
    Returnerer top_n med signaler + name.
    """
    if df_universe is None or df_universe.empty:
        return pd.DataFrame()

    u = df_universe.copy()
    u["ticker"] = u["ticker"].astype(str).str.upper().str.strip()
    if "name" not in u.columns:
        u["name"] = ""

    u = u.dropna(subset=["ticker"])
    u = u[u["ticker"] != ""].drop_duplicates(subset=["ticker"])

    tickers = u["ticker"].tolist()
    close = download_close(tickers, period="2y")

    rows = []
    for _, row in u.iterrows():
        t = row["ticker"]
        name = row.get("name", "")

        if t not in close.columns:
            continue

        sig = compute_signals(close[t])
        if sig is None:
            continue

        reasons = []
        if sig["B_Buy"].startswith("🟢"):
            reasons.append("Buy-early: trend OK + RSI i buy-range og stigende")
        if sig["C_Timing"].startswith("🟡"):
            reasons.append("Take profit: RSI høj")
        if sig["A_Risk"] in ["⚠️", "🚨"]:
            reasons.append("Risiko: vol/drawdown/trend-brud")

        rows.append({
            "Ticker": t,
            "Navn": name,
            **sig,
            "Hvorfor": " | ".join(reasons) if reasons else "Stærkt setup (score)"
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["BuyFlag"] = out["B_Buy"].astype(str).str.startswith("🟢")
    out = out.sort_values(["BuyFlag", "Score"], ascending=[False, False]).drop(columns=["BuyFlag"])
    return out.head(top_n)
