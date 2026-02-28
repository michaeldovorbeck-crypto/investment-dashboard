import re
from datetime import datetime
import requests
import pdfplumber
from io import BytesIO

BASE = "https://www.stoxx.com/document/Reports/SelectionList/{year}/{monthname}/sl_sxxp_{yyyymm}.pdf"

MONTHNAMES = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]

def _try_download_latest_pdf(max_months_back: int = 18):
    today = datetime.utcnow()
    y, m = today.year, today.month

    for back in range(max_months_back):
        yy = y
        mm = m - back
        while mm <= 0:
            mm += 12
            yy -= 1

        monthname = MONTHNAMES[mm - 1]
        yyyymm = f"{yy}{mm:02d}"
        url = BASE.format(year=yy, monthname=monthname, yyyymm=yyyymm)

        r = requests.get(url, timeout=30)
        if r.status_code == 200 and "pdf" in r.headers.get("content-type","").lower():
            return url, r.content

    raise RuntimeError("Could not find a recent STOXX selection list PDF (sl_sxxp_YYYYMM.pdf).")

def _ric_to_yahoo(ric: str):
    ric = ric.strip()

    # Swiss SIX: RIC ".S" -> Yahoo ".SW"
    if ric.endswith(".S"):
        return ric[:-2] + ".SW"

    # Most other common ones already match Yahoo: .DE .PA .AS .L .CO .ST etc.
    if "." not in ric:
        return None

    return ric

def get_stoxx600_yahoo_tickers():
    url, pdf_bytes = _try_download_latest_pdf()

    ric_pattern = re.compile(r"\b[A-Z0-9\-/]+?\.[A-Z]{1,3}\b")
    rics = set()

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for ric in ric_pattern.findall(text):
                rics.add(ric)

    tickers = []
    for ric in sorted(rics):
        y = _ric_to_yahoo(ric)
        if y:
            tickers.append(y)

    # Deduplicate while keeping order
    seen = set()
    out = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)

    return out, url
