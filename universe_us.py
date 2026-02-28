import os
import pandas as pd
import requests

WIKI_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
FALLBACK_CSV = "data/sp500.csv"

def get_sp500_universe():
    """
    Returnerer (df, status_message)
    df har kolonner: ticker, name
    Fejler Wikipedia, returneres fallback CSV hvis den findes – ellers tom df.
    """
    # 1) Prøv Wikipedia
    try:
        r = requests.get(
            WIKI_SP500,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code != 200:
            raise RuntimeError(f"Wikipedia HTTP {r.status_code}")

        tables = pd.read_html(r.text)
        df = tables[0].copy()
        df = df.rename(columns={"Symbol": "ticker", "Security": "name"})
        df["ticker"] = df["ticker"].astype(str).str.replace(".", "-", regex=False)  # BRK.B -> BRK-B
        df["name"] = df["name"].astype(str)

        out = df[["ticker", "name"]].dropna().drop_duplicates(subset=["ticker"])
        return out, "S&P500 hentet fra Wikipedia (cachet)."

    except Exception as e:
        # 2) Fallback: lokal CSV (hvis du opretter den)
        if os.path.exists(FALLBACK_CSV):
            df = pd.read_csv(FALLBACK_CSV)
            if "ticker" in df.columns:
                if "name" not in df.columns:
                    df["name"] = ""
                df = df[["ticker", "name"]].dropna().drop_duplicates(subset=["ticker"])
                return df, f"S&P500 hentet fra fallback CSV (Wikipedia fejlede: {e})"

        # 3) Returnér tomt resultat i stedet for crash
        empty = pd.DataFrame(columns=["ticker", "name"])
        return empty, f"S&P500 kunne ikke hentes lige nu (Wikipedia fejlede: {e})."
