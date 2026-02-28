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

    # A: risiko
    if (not trend_up) or (dd < -0.15):
        A = "🚨"
    elif vol > 5:
        A = "⚠️"
    else:
        A = "✅"

    # B: buy early
    buy_early = trend_up and (RSI_BUY_LOW < rsi_now < RSI_BUY_HIGH) and (np.isfinite(rsi_prev) and rsi_now > rsi_prev)
    B = "🟢" if buy_early else "❌"

    # C: timing
    if rsi_now > RSI_TAKE_PROFIT:
        C = "🟡 TAKE_PROFIT"
    elif not trend_up:
        C = "🔴 EXIT_RISK"
    else:
        C = "🔵 HOLD/ADD"

    # Score 0-100 (simpel momentum + stabilitet)
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

def screen_universe(tickers, top_n=10):
    tickers = [t.strip().upper() for t in tickers if t and isinstance(t, str)]
    tickers = sorted(set(tickers))
    if not tickers:
        return pd.DataFrame()

    close = download_close(tickers, period="2y")

    rows = []
    for t in tickers:
        if t not in close.columns:
            continue
        sig = compute_signals(close[t])
        if sig is None:
            continue

        reasons = []
        if sig["B_Buy"].startswith("🟢"):
            reasons.append("Buy early: trend OK + RSI improving")
        if sig["C_Timing"].startswith("🟡"):
            reasons.append("Take profit watch: RSI high")
        if sig["A_Risk"] in ["⚠️", "🚨"]:
            reasons.append("Risk: vol/drawdown/trend break")

        rows.append({"Ticker": t, **sig, "Why": " | ".join(reasons) if reasons else "Strong/OK setup"})

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["BuyFlag"] = out["B_Buy"].astype(str).str.startswith("🟢")
    out = out.sort_values(["BuyFlag", "Score"], ascending=[False, False]).drop(columns=["BuyFlag"])
    return out.head(top_n)
