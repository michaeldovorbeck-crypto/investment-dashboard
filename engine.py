import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.cluster import AgglomerativeClustering

# ---- Konfiguration (tilpas her) ----
THEMES = {
    "Market": ["SPY"],
    "Nasdaq/Tech": ["QQQ", "XLK"],
    "Semis": ["SOXX"],
    "SmallCaps": ["IWM"],
    "CryptoProxy": ["BITO"],
}

DEFAULT_PORTFOLIO = [
    "NVDA", "TSLA", "MSFT", "ARKQ", "META"
]

CLUSTER_WINDOW_DAYS = 126
N_CLUSTERS = 6

RSI_BUY_LOW = 35
RSI_BUY_HIGH = 50
RSI_TAKE_PROFIT = 70

# -----------------------------------

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

def total_return(series, days):
    if len(series) <= days:
        return np.nan
    return series.pct_change(days).iloc[-1]

def market_regime(close, baseline="SPY"):
    if baseline not in close.columns:
        return "UNKNOWN"
    s = close[baseline].dropna()
    if len(s) < 220:
        return "UNKNOWN"
    ma200 = s.rolling(200).mean().iloc[-1]
    return "RISK_ON" if s.iloc[-1] > ma200 else "RISK_OFF"

def theme_ranking(close, baseline="SPY"):
    spy = close.get(baseline)
    rows = []
    for theme, tks in THEMES.items():
        cols = [c for c in tks if c in close.columns]
        if not cols or spy is None:
            continue
        theme_px = close[cols].mean(axis=1).dropna()
        spy_px = spy.dropna()
        idx = theme_px.index.intersection(spy_px.index)
        if len(idx) < 260:
            continue

        theme_px = theme_px.loc[idx]
        spy_px = spy_px.loc[idx]

        rs_1w = total_return(theme_px, 5) - total_return(spy_px, 5)
        rs_1m = total_return(theme_px, 21) - total_return(spy_px, 21)
        rs_3m = total_return(theme_px, 63) - total_return(spy_px, 63)

        ma200 = theme_px.rolling(200).mean().iloc[-1]
        trend_ok = theme_px.iloc[-1] > ma200
        theme_rsi = rsi(theme_px).iloc[-1]
        accel = rs_1m - (rs_3m / 3) if pd.notna(rs_3m) else np.nan

        score = (
            40 * (rs_3m if pd.notna(rs_3m) else 0) +
            35 * (rs_1m if pd.notna(rs_1m) else 0) +
            15 * (rs_1w if pd.notna(rs_1w) else 0) +
            10 * (1 if trend_ok else 0)
        )
        rows.append([theme, score, rs_1w, rs_1m, rs_3m, accel, theme_rsi, trend_ok])

    df = pd.DataFrame(rows, columns=["Theme","ThemeScore","RS_1W","RS_1M","RS_3M","Accel","RSI","TrendOK"])
    return df.sort_values("ThemeScore", ascending=False)

def cluster_map_from_close(close):
    rets = close.pct_change().dropna()
    X = rets.tail(CLUSTER_WINDOW_DAYS)
    corr = X.corr().fillna(0)
    dist = (1 - corr).clip(lower=0)

    n = min(N_CLUSTERS, len(corr.columns))
    if n < 2:
        return pd.DataFrame({"Ticker": corr.columns, "Cluster": [0]*len(corr.columns)})

    model = AgglomerativeClustering(n_clusters=n, metric="precomputed", linkage="average")
    labels = model.fit_predict(dist.values)
    return pd.DataFrame({"Ticker": corr.columns, "Cluster": labels})

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
        "MA50": float(ma50.iloc[-1]),
        "MA200": float(ma200.iloc[-1]),
        "Last": float(close.iloc[-1]),
    }

def run_engine(portfolio=None):
    portfolio = portfolio or DEFAULT_PORTFOLIO

    universe = sorted(set(portfolio + sum(THEMES.values(), [])))
    close = download_close(universe, period="2y")

    regime = market_regime(close, baseline="SPY")
    themes = theme_ranking(close, baseline="SPY")
    clusters = cluster_map_from_close(close)

    rows = []
    for t in portfolio:
        if t not in close.columns:
            continue
        sig = compute_signals(close[t])
        if sig is None:
            continue
        cl = clusters.loc[clusters["Ticker"] == t, "Cluster"]
        rows.append({"Ticker": t, "Cluster": int(cl.iloc[0]) if len(cl) else None, **sig})

    signals = pd.DataFrame(rows).sort_values("Score", ascending=False)

    # Portefølje temperatur (lav = god)
    if len(signals):
        trend_breadth = signals["TrendUp"].mean()
        risk_flags = (signals["A_Risk"] != "✅").mean()
        temp = int(round(100 * (0.6*(1-trend_breadth) + 0.4*risk_flags)))
    else:
        temp, trend_breadth, risk_flags = None, None, None

    # Vægtforslag: Score/Vol
    if len(signals):
        vol = signals["Vol20"].replace(0, np.nan)
        raw = (signals["Score"] / vol).replace([np.inf, -np.inf], np.nan).fillna(0)
        signals["SuggestedWeight"] = (raw / raw.sum()).round(4) if raw.sum() else 0.0
    else:
        signals["SuggestedWeight"] = []

    meta = {
        "MarketRegime": regime,
        "PortfolioTemperature": temp,
        "TrendBreadth": None if trend_breadth is None else float(trend_breadth),
        "RiskFlagShare": None if risk_flags is None else float(risk_flags),
    }

    return signals, themes, meta, close
