# PoliticianStockAI

An AI agent that scans public congressional stock trading disclosures (via the
[Financial Modeling Prep](https://site.financialmodelingprep.com/) Senate/House disclosure
APIs), flags notable trading patterns (high volume, cross-politician overlap, cross-chamber
overlap, buy/sell skew, unusual volume spikes), and uses web research (Serper + OpenAI) to
explain what's likely driving the activity. Results are shown in a Streamlit dashboard.

## Prerequisites

- Python 3.11+ (3.12 recommended)
- An OpenAI API key
- A [Serper](https://serper.dev) API key
- A [Financial Modeling Prep](https://site.financialmodelingprep.com/) API key (free tier works)

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
cp .env.example .env   # then fill in OPENAI_API_KEY, SERPER_API_KEY, FMP_API_KEY
```

## Smoke test the data source

```bash
python scripts/smoke_test_fmp.py
```

Confirms the FMP API key works and returns real Senate/House trade disclosures. Note: the
free tier only supports the "latest" endpoints (most recent ~100 disclosures per chamber,
no pagination) — the app's SQLite cache accumulates history across repeated refreshes.

## Run the dashboard

```bash
streamlit run app.py
```

Click "Refresh / Scan" to fetch trades, run pattern detection, and generate AI research
reports for newly flagged tickers (reports are cached for 24h to avoid redundant OpenAI/Serper
spend).

## Run tests / lint

```bash
pytest tests/
ruff check .
```

## Deployment

Hosted on [Streamlit Community Cloud](https://streamlit.io/cloud) (free): connect this
GitHub repo, point at `app.py`, and set `OPENAI_API_KEY`, `SERPER_API_KEY`, and `FMP_API_KEY`
under the app's Secrets (see `.streamlit/secrets.toml.example`). No Docker/Node.js needed —
the data source is a plain REST API.

Note: SQLite storage lives on the app's local filesystem, which is ephemeral on restart —
the cache rebuilds automatically on the next refresh. Acceptable for the on-demand,
single-instance v1 design.
