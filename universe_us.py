import pandas as pd
import requests

WIKI_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

def get_sp500_universe():
    """
    Returnerer DataFrame med kolonner: ticker, name
    Henter listen fra Wikipedia (stabilt nok til daglig brug).
    """
    r = requests.get(WIKI_SP500, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(r.text)
    df = tables[0].copy()

    # Wikipedia kolonner: Symbol, Security
    df = df.rename(columns={"Symbol": "ticker", "Security": "name"})
    df["ticker"] = df["ticker"].astype(str).str.replace(".", "-", regex=False)  # BRK.B -> BRK-B for Yahoo
    df["name"] = df["name"].astype(str)

    return df[["ticker", "name"]]
